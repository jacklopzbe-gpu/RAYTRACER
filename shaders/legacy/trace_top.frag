// trace.frag - main path tracing pixel shader (TouchDesigner GLSL TOP)
// TAREA 12: + interpolated normals/uv, tangent frames and material maps (inputs 1-4).
// Input 0: previous accumulation (Feedback TOP). Output: rgb = running mean (linear), a = sample count.
#include "common_glsl"

uniform mat4 uCamToWorld;   // op('cam1').worldTransform
uniform vec4 uCamParams;    // x = fov (deg, horizontal)
uniform vec4 uLightPos;     // xyz = rect light center
uniform vec4 uLightSize;    // x = half width (u), y = half depth (v)
uniform vec4 uLightColor;   // rgb = color, w = intensity (radiance multiplier)
uniform vec4 uAccum;        // x = sample index (0 = restart), y = max bounces, z = radiance clamp, w = NEE on/off (test)
uniform vec4 uEnv;          // rgb = sky color, w = intensity
uniform vec4 uMat2;         // metal sphere: x = metallic, y = roughness
uniform vec4 uMat3;         // box: x = metallic, y = roughness
uniform vec4 uMat4;         // glass sphere: x = ior, y = absorption strength, zw unused
uniform vec4 uEmit;         // emissive sphere: rgb = color, w = intensity (0 = disabled)
uniform vec4 uMeshBound;    // bounding sphere of the mesh: xyz = center, w = radius (w <= 0 disables the mesh)
uniform vec4 uMeshMat;      // mesh material: x = metallic, y = roughness, z = unused, w = unused
uniform vec4 uMeshColor;    // rgb = albedo
uniform vec4 uMeshMaps;     // toggles: x = albedo map, y = rough/metal map (r = roughness, g = metallic), z = normal map, w = emit map
// Input 1 = material atlas (2x2): quadrant 0 = albedo (BL), 1 = rough/metal (BR), 2 = normal (TL), 3 = emit (TR)
uniform vec4 uMeshMapParams;// x = normal map strength, y = emit intensity, z = uv tiling, w = unused
// POP buffers (Buffers page): VP = positions, VN = normals, VT = texture coords (vertex class, 3 per triangle)

out vec4 fragColor;

// ---------------------------------------------------------------- scene
#define MAT_FLOOR   0
#define MAT_RED     1
#define MAT_METAL   2
#define MAT_BOX     3
#define MAT_GLASS   4
#define MAT_RECT    5   // rect area light (emissive quad)
#define MAT_EMISPH  6   // small emissive sphere
#define MAT_MESH    7   // triangle mesh from the POP

const vec3 GLASS_C = vec3(0.0, -0.3, 2.2);
const float GLASS_R = 0.7;
const vec3 EMI_C = vec3(-2.6, 0.2, 1.6);
const float EMI_R = 0.25;

RectLight getRectLight()
{
	RectLight l;
	l.c = uLightPos.xyz;
	l.u = vec3(1.0, 0.0, 0.0);
	l.v = vec3(0.0, 0.0, 1.0);
	l.hsize = uLightSize.xy;
	l.n = vec3(0.0, -1.0, 0.0);          // emits downwards
	l.L = uLightColor.rgb * uLightColor.w;
	return l;
}

bool hitRect(Ray r, RectLight l, float tMax, inout Hit h, int mat)
{
	float denom = dot(l.n, r.d);
	if (abs(denom) < 1e-6) return false;
	float t = dot(l.c - r.o, l.n) / denom;
	if (t <= EPS || t >= tMax || t >= h.t) return false;
	vec3 p = r.o + r.d * t;
	vec3 d = p - l.c;
	if (abs(dot(d, l.u)) > l.hsize.x || abs(dot(d, l.v)) > l.hsize.y) return false;
	h.t = t; h.p = p; h.n = denom < 0.0 ? l.n : -l.n; h.inside = denom > 0.0; h.mat = mat;
	return true;
}

// Brute force over every triangle of the POP mesh (Tarea 11). BVH comes later.
void hitMesh(Ray r, float tMax, inout Hit h)
{
	if (uMeshBound.w <= 0.0) return;
	if (!intersectsSphere(r, uMeshBound.xyz, uMeshBound.w)) return;
	uint nv = TDBufferLength_VP();
	uint ntri = nv / 3u;
	float tBest = min(tMax, h.t);
	int best = -1; vec2 bb = vec2(0.0), bary;
	for (uint i = 0u; i < ntri; ++i) {
		vec3 a = TDBuffer_VP(i * 3u), b = TDBuffer_VP(i * 3u + 1u), c = TDBuffer_VP(i * 3u + 2u);
		if (hitTriangle(r, a, b, c, tMax, tBest, bary)) { best = int(i); bb = bary; }
	}
	if (best < 0) return;
	uint i0 = uint(best) * 3u;
	vec3 a = TDBuffer_VP(i0), b = TDBuffer_VP(i0 + 1u), c = TDBuffer_VP(i0 + 2u);
	vec3 ng = normalize(cross(b - a, c - a));      // geometric normal
	h.t = tBest; h.p = r.o + r.d * tBest;
	h.inside = dot(ng, r.d) > 0.0;
	h.n = h.inside ? -ng : ng;
	h.mat = MAT_MESH; h.prim = best; h.bary = bb;
	// interpolated attributes
	float w0 = 1.0 - bb.x - bb.y;
	vec3 n0 = TDBuffer_VN(i0), n1 = TDBuffer_VN(i0 + 1u), n2 = TDBuffer_VN(i0 + 2u);
	vec2 t0 = TDBuffer_VT(i0).xy, t1 = TDBuffer_VT(i0 + 1u).xy, t2 = TDBuffer_VT(i0 + 2u).xy;
	vec3 ns = normalize(w0 * n0 + bb.x * n1 + bb.y * n2);
	if (dot(ns, ns) < 0.5 || any(isnan(ns))) ns = ng;
	if (dot(ns, h.n) < 0.0) ns = -ns;              // keep shading normal on the visible side
	h.ns = ns;
	h.uv = w0 * t0 + bb.x * t1 + bb.y * t2;
	// tangent from uv derivatives
	vec3 dp1 = b - a, dp2 = c - a; vec2 duv1 = t1 - t0, duv2 = t2 - t0;
	float det = duv1.x * duv2.y - duv1.y * duv2.x;
	vec3 tg = abs(det) > 1e-12 ? (dp1 * duv2.y - dp2 * duv1.y) / det : vec3(0.0);
	tg = tg - ns * dot(ns, tg);
	h.tg = dot(tg, tg) > 1e-12 ? normalize(tg) : vec3(0.0);
}

Hit intersectScene(Ray r, float tMax)
{
	Hit h = noHit();
	hitPlane (r, vec3(0.0, -1.0, 0.0), vec3(0.0, 1.0, 0.0), tMax, h, MAT_FLOOR);
	hitSphere(r, vec3(-1.3, 0.0, 0.0), 1.0, tMax, h, MAT_RED);
	hitSphere(r, vec3( 1.3, 0.0, 0.0), 1.0, tMax, h, MAT_METAL);
	hitBox   (r, vec3(-0.6, -1.0, -3.0), vec3(0.6, 0.6, -1.8), tMax, h, MAT_BOX);
	hitSphere(r, GLASS_C, GLASS_R, tMax, h, MAT_GLASS);
	hitRect  (r, getRectLight(), tMax, h, MAT_RECT);
	if (uEmit.w > 0.0) hitSphere(r, EMI_C, EMI_R, tMax, h, MAT_EMISPH);
	hitMesh(r, tMax, h);
	return h;
}

bool occluded(Ray r, float tMax)
{
	Hit h = intersectScene(r, tMax);
	return h.mat >= 0;
}

Material getMaterial(int id)
{
	Material m; m.albedo = vec3(0.8); m.emit = vec3(0.0); m.metallic = 0.0; m.roughness = 0.5;
	m.transmission = 0.0; m.ior = 1.5; m.absorb = vec3(0.0);
	if      (id == MAT_FLOOR)  { m.albedo = vec3(0.7); }
	else if (id == MAT_RED)    { m.albedo = vec3(0.8, 0.15, 0.1); }
	else if (id == MAT_METAL)  { m.albedo = vec3(0.9, 0.9, 0.85); m.metallic = uMat2.x; m.roughness = uMat2.y; }
	else if (id == MAT_BOX)    { m.albedo = vec3(0.15, 0.4, 0.8);  m.metallic = uMat3.x; m.roughness = uMat3.y; }
	else if (id == MAT_GLASS)  { m.albedo = vec3(1.0); m.transmission = 1.0; m.ior = uMat4.x;
	                             m.absorb = vec3(0.9, 0.15, 0.55) * uMat4.y; }   // absorbs red+blue -> green tint
	else if (id == MAT_RECT)   { m.albedo = vec3(0.0); m.emit = uLightColor.rgb * uLightColor.w; }
	else if (id == MAT_EMISPH) { m.albedo = vec3(0.0); m.emit = uEmit.rgb * uEmit.w; }
	else if (id == MAT_MESH)   { m.albedo = uMeshColor.rgb; m.metallic = uMeshMat.x; m.roughness = uMeshMat.y; }
	return m;
}

// Sample quadrant q of the material atlas (input 1) with repeat wrapping inside the quadrant.
vec4 sampleMap(int q, vec2 uv)
{
	vec2 texel = uTD2DInfos[1].res.xy;                       // 1/width, 1/height of the atlas
	vec2 luv = clamp(fract(uv), texel * 2.0, 1.0 - texel * 2.0) * 0.5;
	vec2 off = vec2(float(q & 1), float(q >> 1)) * 0.5;
	return textureLod(sTD2DInputs[1], luv + off, 0.0);
}

// Apply the material maps (atlas in input 1) and normal mapping to a mesh hit.
void applyMeshMaps(inout Hit h, inout Material m)
{
	vec2 uv = h.uv * uMeshMapParams.z;
	if (uMeshMaps.x > 0.5) m.albedo *= sampleMap(0, uv).rgb;
	if (uMeshMaps.y > 0.5) { vec4 rm = sampleMap(1, uv); m.roughness = rm.r; m.metallic = rm.g; }
	if (uMeshMaps.w > 0.5) m.emit = sampleMap(3, uv).rgb * uMeshMapParams.y;
	if (uMeshMaps.z > 0.5 && dot(h.tg, h.tg) > 0.5) {
		vec3 nm = sampleMap(2, uv).xyz * 2.0 - 1.0;
		nm.xy *= uMeshMapParams.x;
		vec3 bt = cross(h.ns, h.tg);
		vec3 np = normalize(h.tg * nm.x + bt * nm.y + h.ns * max(nm.z, 0.05));
		if (dot(np, h.n) > 0.0) h.ns = np;         // never flip below the geometric surface
	}
}

// ---------------------------------------------------------------- lights (for NEE)
int numLights() { return uEmit.w > 0.0 ? 2 : 1; }

// Sample a point on light 'idx'. Returns position, normal, emitted radiance and the area pdf.
void sampleLight(int idx, vec2 xi, out vec3 pos, out vec3 n, out vec3 Le, out float pdfA)
{
	if (idx == 0) {
		RectLight l = getRectLight();
		pos = rectLightPoint(l, xi); n = l.n; Le = l.L; pdfA = 1.0 / rectLightArea(l);
	} else {
		// uniform on the sphere surface
		float z = 1.0 - 2.0 * xi.x;
		float rr = sqrt(max(0.0, 1.0 - z * z));
		float phi = 2.0 * PI * xi.y;
		n = vec3(rr * cos(phi), rr * sin(phi), z);
		pos = EMI_C + n * EMI_R;
		Le = uEmit.rgb * uEmit.w;
		pdfA = 1.0 / (4.0 * PI * EMI_R * EMI_R);
	}
}

// Area pdf of the light that owns material 'mat' (for MIS when a BSDF ray hits an emitter).
float lightPdfA(int mat)
{
	if (mat == MAT_RECT)   return 1.0 / rectLightArea(getRectLight());
	if (mat == MAT_EMISPH) return 1.0 / (4.0 * PI * EMI_R * EMI_R);
	return 0.0;
}

float misPower(float a, float b) { float a2 = a * a, b2 = b * b; return a2 / max(a2 + b2, 1e-10); }

// Next event estimation with MIS against the BSDF pdf.
vec3 directLight(Hit h, Material m, vec3 wo)
{
	int nl = numLights();
	int idx = min(int(rand() * float(nl)), nl - 1);
	vec3 lp, ln, Le; float pdfA;
	sampleLight(idx, rand2(), lp, ln, Le, pdfA);
	pdfA /= float(nl);
	vec3 toL = lp - h.p;
	float d2 = dot(toL, toL);
	float d = sqrt(d2);
	vec3 wi = toL / d;
	float cosL = dot(ln, -wi);
	if (cosL <= 0.0 || dot(h.n, wi) <= 0.0 || dot(h.ns, wi) <= 0.0) return vec3(0.0);
	Ray sr; sr.o = h.p + h.n * EPS * 4.0; sr.d = wi;
	if (occluded(sr, d - EPS * 8.0)) return vec3(0.0);
	float pdfB;
	vec3 fcos = bsdfEval(m, h.ns, wo, wi, pdfB);         // f * cos (shading normal)
	float pdfLsolid = pdfA * d2 / cosL;                   // area pdf -> solid angle
	float w = misPower(pdfLsolid, pdfB);
	return fcos * Le * w / pdfLsolid;
}

// ---------------------------------------------------------------- path
vec3 tracePath(Ray r, int maxBounces, bool useNEE)
{
	vec3 radiance = vec3(0.0);
	vec3 throughput = vec3(1.0);
	float prevPdfB = 0.0;        // pdf of the last BSDF sample (solid angle)
	bool  prevDelta = true;      // camera / specular: emitters counted fully
	vec3  medium = vec3(0.0);    // absorption of the medium the ray currently travels in

	for (int bounce = 0; bounce <= maxBounces; ++bounce) {
		Hit h = intersectScene(r, INF);
		if (h.mat < 0) { radiance += throughput * uEnv.rgb * uEnv.w; break; }
		throughput *= exp(-medium * h.t);                 // Beer-Lambert along the segment
		Material m = getMaterial(h.mat);
		if (h.mat == MAT_MESH) applyMeshMaps(h, m);
		vec3 wo = -r.d;

		// emissive surface hit by the path
		if (dot(m.emit, m.emit) > 0.0) {
			if (!h.inside) {
				float w = 1.0;
				if (useNEE && !prevDelta) {
					float cosL = max(dot(h.n, wo), 0.0);
					float pdfLsolid = lightPdfA(h.mat) / float(numLights()) * h.t * h.t / max(cosL, 1e-6);
					w = misPower(prevPdfB, pdfLsolid);
				}
				radiance += throughput * m.emit * w;
			}
			if (h.mat != MAT_MESH) break;                 // pure lights stop the path; an emissive mesh keeps bouncing
		}

		if (m.transmission > 0.0) {
			// smooth dielectric: exact Fresnel, reflect or refract
			float eta = h.inside ? m.ior : 1.0 / m.ior;   // n_from / n_to
			float cosI = clamp(dot(wo, h.n), 0.0, 1.0);
			float sin2T = eta * eta * (1.0 - cosI * cosI);
			float F = 1.0;
			vec3 wt = vec3(0.0);
			if (sin2T < 1.0) {
				float cosT = sqrt(1.0 - sin2T);
				float rs = (eta * cosI - cosT) / (eta * cosI + cosT);
				float rp = (cosI - eta * cosT) / (cosI + eta * cosT);
				F = 0.5 * (rs * rs + rp * rp);
				wt = normalize(-wo * eta + h.n * (eta * cosI - cosT));
			}
			if (rand() < F) {
				r.d = reflect(-wo, h.n);
				r.o = h.p + h.n * EPS * 4.0;
			} else {
				r.d = wt;
				r.o = h.p - h.n * EPS * 4.0;
				medium = h.inside ? vec3(0.0) : m.absorb;    // entering or leaving the glass
			}
			throughput *= m.albedo;
			prevDelta = true;
			continue;
		}

		if (useNEE) radiance += throughput * directLight(h, m, wo);
		if (bounce == maxBounces) break;

		vec3 wi; float pdf;
		vec3 w = bsdfSample(m, h.ns, wo, vec3(rand2(), rand()), wi, pdf);
		if (pdf <= 0.0 || dot(wi, h.n) <= 0.0) break;   // shading normal may point below the surface
		throughput *= w;
		prevPdfB = pdf;
		prevDelta = false;
		r.o = h.p + h.n * EPS * 4.0;
		r.d = wi;

		// Russian roulette after a few bounces
		if (bounce >= 2) {
			float p = clamp(max(throughput.r, max(throughput.g, throughput.b)), 0.05, 0.95);
			if (rand() > p) break;
			throughput /= p;
		}
	}
	return radiance;
}

void main()
{
	uint sampleIndex = uint(max(uAccum.x, 0.0));
	uvec2 pix = uvec2(gl_FragCoord.xy);
	rngSeed(pix, sampleIndex);

	// jitter inside the pixel for anti-aliasing
	vec2 jitter = (rand2() - 0.5) * uTDOutputInfo.res.xy;
	float aspect = uTDOutputInfo.res.z / uTDOutputInfo.res.w;
	Ray r = cameraRay(vUV.st + jitter, uCamToWorld, uCamParams.x, aspect);

	vec3 col = tracePath(r, int(uAccum.y), uAccum.w > 0.5);
	col = max(col, vec3(0.0));
	if (uAccum.z > 0.0) col = min(col, vec3(uAccum.z));     // firefly clamp
	if (any(isnan(col)) || any(isinf(col))) col = vec3(0.0);

	// progressive mean: acc_n = acc_{n-1} + (x - acc_{n-1}) / n
	vec4 prev = texelFetch(sTD2DInputs[0], ivec2(gl_FragCoord.xy), 0);
	float n = float(sampleIndex) + 1.0;
	vec3 acc = (sampleIndex == 0u) ? col : prev.rgb + (col - prev.rgb) / n;
	fragColor = TDOutputSwizzle(vec4(acc, n));
}
