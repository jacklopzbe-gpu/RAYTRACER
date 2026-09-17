// trace.glsl - path tracing kernel as a GLSL POP compute shader (one thread per pixel).
// Hardware ray tracing (rayQueryEXT) for the mesh via the Collision POP 'uAS'; analytic objects as before.
//
// Inputs (set by td/build_network.py):
//   input 0            : pix_grid (Resw x Resh points, id = y * W + x)
//   input 1 (In POPs)  : mesh_verts (vertex attributes VP, VN, Tex, 3 per triangle, same order as the collision POP)
//   uAS                : acceleration structure of mesh_tri
//   uCamC0..3          : columns of the camera world transform (vec4 uniforms; a matrix uniform is NOT refreshed reliably on POPs)
//   sPrev              : previous accumulation (Feedback TOP), sAtlas : material atlas 2x2, sEnv : equirect environment
//   uScene             : x = floor on, y = floor height, z = demo objects on, w = env map on
//   Uniforms are declared by the POP (Vectors/Matrices pages), NOT here.
// Output: Color = (running mean rgb, sample count)
#include "common_glsl"

#define MAT_FLOOR   0
#define MAT_RED     1
#define MAT_METAL   2
#define MAT_BOX     3
#define MAT_GLASS   4
#define MAT_RECT    5   // rect area light (emissive quad)
#define MAT_EMISPH  6   // small emissive sphere
#define MAT_MESH    7   // triangle mesh (hardware RT)

const vec3 GLASS_C = vec3(0.0, -0.3, 2.2);
const float GLASS_R = 0.7;
const vec3 EMI_C = vec3(-2.6, 0.2, 1.6);
const float EMI_R = 0.25;

// ---------------------------------------------------------------- scene
RectLight getRectLight()
{
	RectLight l;
	l.c = uLightPos.xyz;
	l.u = vec3(1.0, 0.0, 0.0);
	l.v = vec3(0.0, 0.0, 1.0);
	l.hsize = uLightSize.xy;
	l.n = vec3(0.0, -1.0, 0.0);
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
	h.t = t; h.p = p; h.n = denom < 0.0 ? l.n : -l.n; h.inside = denom > 0.0; h.mat = mat; h.ns = h.n; h.uv = vec2(0.0); h.tg = vec3(0.0);
	return true;
}

// Hardware ray query against the mesh. Only accepts hits closer than h.t.
void hitMesh(Ray r, float tMax, inout Hit h)
{
	if (uMeshBound.w <= 0.0) return;                 // mesh disabled from the parameters
	float tmax = min(tMax, h.t);
	if (tmax <= EPS) return;
	rayQueryEXT rq;
	rayQueryInitializeEXT(rq, uAS, gl_RayFlagsOpaqueEXT, 0xFF, r.o, EPS, r.d, tmax);
	while (rayQueryProceedEXT(rq)) { }
	if (rayQueryGetIntersectionTypeEXT(rq, true) != gl_RayQueryCommittedIntersectionTriangleEXT) return;
	float t = rayQueryGetIntersectionTEXT(rq, true);
	if (t >= h.t) return;
	uint prim = uint(rayQueryGetIntersectionPrimitiveIndexEXT(rq, true));
	vec2 bb = rayQueryGetIntersectionBarycentricsEXT(rq, true);
	bool front = rayQueryGetIntersectionFrontFaceEXT(rq, true);
	uint i0 = prim * 3u;
	vec3 a = TDInVert_VP(1u, i0, 0u), b = TDInVert_VP(1u, i0 + 1u, 0u), c = TDInVert_VP(1u, i0 + 2u, 0u);
	vec3 ng = normalize(cross(b - a, c - a));
	h.t = t; h.p = r.o + r.d * t;
	h.inside = dot(ng, r.d) > 0.0;
	h.n = h.inside ? -ng : ng;
	h.mat = MAT_MESH; h.prim = int(prim); h.bary = bb;
	float w0 = 1.0 - bb.x - bb.y;
	h.matId = int(TDInVert_VM(1u, i0, 0u) + 0.5);                       // per-vertex material id (0 = params, 1 = emissive, 2 = glass)
	h.vcol = w0 * TDInVert_VC(1u, i0, 0u) + bb.x * TDInVert_VC(1u, i0 + 1u, 0u) + bb.y * TDInVert_VC(1u, i0 + 2u, 0u);
	vec3 n0 = TDInVert_VN(1u, i0, 0u), n1 = TDInVert_VN(1u, i0 + 1u, 0u), n2 = TDInVert_VN(1u, i0 + 2u, 0u);
	vec2 t0 = TDInVert_Tex(1u, i0, 0u).xy, t1 = TDInVert_Tex(1u, i0 + 1u, 0u).xy, t2 = TDInVert_Tex(1u, i0 + 2u, 0u).xy;
	vec3 ns = normalize(w0 * n0 + bb.x * n1 + bb.y * n2);
	if (dot(ns, ns) < 0.5 || any(isnan(ns))) ns = ng;
	if (dot(ns, h.n) < 0.0) ns = -ns;
	h.ns = ns;
	h.uv = w0 * t0 + bb.x * t1 + bb.y * t2;
	vec3 dp1 = b - a, dp2 = c - a; vec2 duv1 = t1 - t0, duv2 = t2 - t0;
	float det = duv1.x * duv2.y - duv1.y * duv2.x;
	vec3 tg = abs(det) > 1e-12 ? (dp1 * duv2.y - dp2 * duv1.y) / det : vec3(0.0);
	tg = tg - ns * dot(ns, tg);
	h.tg = dot(tg, tg) > 1e-12 ? normalize(tg) : vec3(0.0);
}

// Shadow-ray occlusion test against the mesh only (any hit).
bool meshOccluded(Ray r, float tMax)
{
	if (uMeshBound.w <= 0.0) return false;
	rayQueryEXT rq;
	rayQueryInitializeEXT(rq, uAS, gl_RayFlagsOpaqueEXT | gl_RayFlagsTerminateOnFirstHitEXT, 0xFF, r.o, EPS, r.d, tMax);
	while (rayQueryProceedEXT(rq)) { }
	return rayQueryGetIntersectionTypeEXT(rq, true) == gl_RayQueryCommittedIntersectionTriangleEXT;
}

Hit intersectAnalytic(Ray r, float tMax)
{
	Hit h = noHit();
	if (uScene.x > 0.5) hitPlane (r, vec3(0.0, uScene.y, 0.0), vec3(0.0, 1.0, 0.0), tMax, h, MAT_FLOOR);
	if (uScene.z > 0.5) {                                                  // demo objects
		hitSphere(r, vec3(-1.3, 0.0, 0.0), 1.0, tMax, h, MAT_RED);
		hitSphere(r, vec3( 1.3, 0.0, 0.0), 1.0, tMax, h, MAT_METAL);
		hitBox   (r, vec3(-0.6, -1.0, -3.0), vec3(0.6, 0.6, -1.8), tMax, h, MAT_BOX);
		hitSphere(r, GLASS_C, GLASS_R, tMax, h, MAT_GLASS);
		if (uEmit.w > 0.0) hitSphere(r, EMI_C, EMI_R, tMax, h, MAT_EMISPH);
	}
	if (uLightColor.w > 0.0) hitRect(r, getRectLight(), tMax, h, MAT_RECT);
	return h;
}

// Environment radiance for a direction (equirectangular map * color * intensity, or flat color)
vec3 environment(vec3 d)
{
	vec3 e = uEnv.rgb * uEnv.w;
	if (uScene.w > 0.5) {
		float u = atan(d.x, -d.z) * (0.5 * INV_PI) + 0.5 + uEnv2.y / 360.0;   // uEnv2.y = rotation (deg)
		float v = asin(clamp(d.y, -1.0, 1.0)) * INV_PI + 0.5;
		e *= textureLod(sEnv, vec2(u, v), 0.0).rgb;
	}
	return e;
}

Hit intersectScene(Ray r, float tMax)
{
	Hit h = intersectAnalytic(r, tMax);
	hitMesh(r, tMax, h);
	return h;
}

// ---------------------------------------------------------------- materials
Material getMaterial(int id)
{
	Material m; m.albedo = vec3(0.8); m.emit = vec3(0.0); m.metallic = 0.0; m.roughness = 0.5;
	m.transmission = 0.0; m.ior = 1.5; m.absorb = vec3(0.0);
	if      (id == MAT_FLOOR)  { m.albedo = uFloor.rgb; m.metallic = uFloorMat.x; m.roughness = uFloorMat.y; }
	else if (id == MAT_RED)    { m.albedo = vec3(0.8, 0.15, 0.1); }
	else if (id == MAT_METAL)  { m.albedo = vec3(0.9, 0.9, 0.85); m.metallic = uMat2.x; m.roughness = uMat2.y; }
	else if (id == MAT_BOX)    { m.albedo = vec3(0.15, 0.4, 0.8);  m.metallic = uMat3.x; m.roughness = uMat3.y; }
	else if (id == MAT_GLASS)  { m.albedo = vec3(1.0); m.transmission = 1.0; m.ior = uMat4.x;
	                             m.absorb = vec3(0.9, 0.15, 0.55) * uMat4.y; }
	else if (id == MAT_RECT)   { m.albedo = vec3(0.0); m.emit = uLightColor.rgb * uLightColor.w; }
	else if (id == MAT_EMISPH) { m.albedo = vec3(0.0); m.emit = uEmit.rgb * uEmit.w; }
	else if (id == MAT_MESH)   { m.albedo = uMeshColor.rgb; m.metallic = uMeshMat.x; m.roughness = uMeshMat.y; }
	return m;
}

vec4 sampleMap(int q, vec2 uv)
{
	vec2 texel = 1.0 / vec2(textureSize(sAtlas, 0));
	vec2 luv = clamp(fract(uv), texel * 2.0, 1.0 - texel * 2.0) * 0.5;
	vec2 off = vec2(float(q & 1), float(q >> 1)) * 0.5;
	return textureLod(sAtlas, luv + off, 0.0);
}

void applyMeshMaps(inout Hit h, inout Material m)
{
	// per-vertex material id / color from the input POP ('mat' and 'Color' attributes, defaults 0 / white)
	m.albedo *= h.vcol.rgb;
	if (h.matId == 1) { m.emit = h.vcol.rgb * uMeshMapParams.y; m.albedo = vec3(0.0); return; }
	if (h.matId == 2) { m.albedo = vec3(1.0); m.transmission = 1.0; m.ior = uMat4.x; m.absorb = (vec3(1.0) - h.vcol.rgb) * uMat4.y; return; }
	if (h.matId == 3) { m.metallic = 1.0; m.roughness = 0.05; return; }   // chrome preset
	vec2 uv = h.uv * uMeshMapParams.z;
	if (uMeshMaps.x > 0.5) m.albedo *= sampleMap(0, uv).rgb;
	if (uMeshMaps.y > 0.5) { vec4 rm = sampleMap(1, uv); m.roughness = rm.r; m.metallic = rm.g; }
	if (uMeshMaps.w > 0.5) m.emit = sampleMap(3, uv).rgb * uMeshMapParams.y;
	if (uMeshMaps.z > 0.5 && dot(h.tg, h.tg) > 0.5) {
		vec3 nm = sampleMap(2, uv).xyz * 2.0 - 1.0;
		nm.xy *= uMeshMapParams.x;
		vec3 bt = cross(h.ns, h.tg);
		vec3 np = normalize(h.tg * nm.x + bt * nm.y + h.ns * max(nm.z, 0.05));
		if (dot(np, h.n) > 0.0) h.ns = np;
	}
}

// ---------------------------------------------------------------- glass FX (uGlassFx: x = dispersion, y = iridescence, z = iridescence scale, w = tinted shadows)
// Thin-film style rainbow: phase depends on view angle and film thickness.
vec3 iridescence(float cosI)
{
	float ph = uGlassFx.z * (1.0 - cosI);
	return 0.5 + 0.5 * cos(2.0 * PI * (ph + vec3(0.0, 0.33, 0.67)));
}

// Transmittance of a shadow ray: glass lets tinted light through instead of blocking it (fake caustics).
vec3 shadowTransmittance(Ray r, float dist)
{
	vec3 T = vec3(1.0);
	float remaining = dist;
	for (int i = 0; i < 4; ++i) {
		Hit h = intersectAnalytic(r, remaining);
		float tm = h.mat >= 0 ? h.t : remaining;
		if (meshOccluded(r, tm)) return vec3(0.0);
		if (h.mat < 0) return T;
		if (h.mat != MAT_GLASS || uGlassFx.w < 0.5) return vec3(0.0);
		Material m = getMaterial(h.mat);
		// entering: pay Fresnel-ish loss; travelling inside: Beer-Lambert over the chord (approx. by next exit)
		if (!h.inside) T *= 0.92 * mix(vec3(1.0), iridescence(max(dot(h.n, -r.d), 0.0)), uGlassFx.y);
		else           T *= exp(-m.absorb * h.t);
		remaining -= h.t;
		r.o = h.p + r.d * EPS * 4.0;
		if (remaining <= EPS) return T;
	}
	return vec3(0.0);
}

// ---------------------------------------------------------------- lights (NEE)
int numLights() { return uEmit.w > 0.0 ? 2 : 1; }

void sampleLight(int idx, vec2 xi, out vec3 pos, out vec3 n, out vec3 Le, out float pdfA)
{
	if (idx == 0) {
		RectLight l = getRectLight();
		pos = rectLightPoint(l, xi); n = l.n; Le = l.L; pdfA = 1.0 / rectLightArea(l);
	} else {
		float z = 1.0 - 2.0 * xi.x;
		float rr = sqrt(max(0.0, 1.0 - z * z));
		float phi = 2.0 * PI * xi.y;
		n = vec3(rr * cos(phi), rr * sin(phi), z);
		pos = EMI_C + n * EMI_R;
		Le = uEmit.rgb * uEmit.w;
		pdfA = 1.0 / (4.0 * PI * EMI_R * EMI_R);
	}
}

float lightPdfA(int mat)
{
	if (mat == MAT_RECT)   return 1.0 / rectLightArea(getRectLight());
	if (mat == MAT_EMISPH) return 1.0 / (4.0 * PI * EMI_R * EMI_R);
	return 0.0;
}

float misPower(float a, float b) { float a2 = a * a, b2 = b * b; return a2 / max(a2 + b2, 1e-10); }

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
	vec3 T = shadowTransmittance(sr, d - EPS * 8.0);
	if (dot(T, T) <= 0.0) return vec3(0.0);
	float pdfB;
	vec3 fcos = bsdfEval(m, h.ns, wo, wi, pdfB);
	float pdfLsolid = pdfA * d2 / cosL;
	float w = misPower(pdfLsolid, pdfB);
	return fcos * Le * T * w / pdfLsolid;
}

// ---------------------------------------------------------------- path
vec3 tracePath(Ray r, int maxBounces, bool useNEE)
{
	vec3 radiance = vec3(0.0);
	vec3 throughput = vec3(1.0);
	float prevPdfB = 0.0;
	bool  prevDelta = true;
	vec3  medium = vec3(0.0);
	int   channel = -1;          // dispersion: wavelength channel chosen at the first glass hit (-1 = none)

	for (int bounce = 0; bounce <= maxBounces; ++bounce) {
		Hit h = intersectScene(r, INF);
		if (h.mat < 0) { if (bounce > 0 || uEnv2.x > 0.5) radiance += throughput * environment(r.d); break; }   // uEnv2.x: env visible to camera
		throughput *= exp(-medium * h.t);
		Material m = getMaterial(h.mat);
		if (h.mat == MAT_MESH) applyMeshMaps(h, m);
		vec3 wo = -r.d;

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
			if (h.mat != MAT_MESH) break;
		}

		if (m.transmission > 0.0) {
			// dispersion: restrict the path to one wavelength channel with a per-channel IOR
			if (uGlassFx.x > 0.0 && channel < 0) {
				channel = min(int(rand() * 3.0), 2);
				vec3 sel = vec3(0.0); sel[channel] = 3.0;
				throughput *= sel;
			}
			float ior = m.ior;
			if (channel >= 0) ior += uGlassFx.x * 0.08 * float(channel - 1);   // red lower, blue higher (Dispersion 1 ~ +-0.08 IOR)
			float eta = h.inside ? ior : 1.0 / ior;
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
				if (!h.inside) throughput *= mix(vec3(1.0), iridescence(cosI), uGlassFx.y);   // iridescent sheen
			} else {
				r.d = wt;
				r.o = h.p - h.n * EPS * 4.0;
				medium = h.inside ? vec3(0.0) : m.absorb;
				if (!h.inside) throughput *= mix(vec3(1.0), iridescence(cosI) * 0.6 + 0.4, uGlassFx.y * 0.7);   // tempered-glass body tint (fake)
			}
			throughput *= m.albedo;
			prevDelta = true;
			continue;
		}

		if (useNEE) radiance += throughput * directLight(h, m, wo);
		if (bounce == maxBounces) break;

		vec3 wi; float pdf;
		vec3 w = bsdfSample(m, h.ns, wo, vec3(rand2(), rand()), wi, pdf);
		if (pdf <= 0.0 || dot(wi, h.n) <= 0.0) break;
		throughput *= w;
		prevPdfB = pdf;
		prevDelta = false;
		r.o = h.p + h.n * EPS * 4.0;
		r.d = wi;

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
	const uint id = TDIndex();
	if (id >= TDNumElements()) return;
	uint W = uint(uRes.x), H = uint(uRes.y);
	uvec2 pix = uvec2(id % W, id / W);
	if (pix.y >= H) return;

	uint sampleIndex = uint(max(uAccum.x, 0.0));
	uint spp = uint(clamp(uAccum2.x, 1.0, 256.0));
	float aspect = uRes.x / uRes.y;
	mat4 camToWorld = mat4(uCamC0, uCamC1, uCamC2, uCamC3);   // columns of cam1.worldTransform (matrix uniforms of the POP go stale)

	// spp samples per cook (offline renders use many)
	vec3 col = vec3(0.0);
	for (uint s = 0u; s < spp; ++s) {
		rngSeed(pix, sampleIndex * spp + s);
		vec2 uv = (vec2(pix) + rand2()) / vec2(W, H);     // jittered pixel center
		Ray r = cameraRay(uv, camToWorld, uCamParams.x, aspect);
		vec3 c = tracePath(r, int(uAccum.y), uAccum.w > 0.5);
		c = max(c, vec3(0.0));
		if (uAccum.z > 0.0) c = min(c, vec3(uAccum.z));
		if (any(isnan(c)) || any(isinf(c))) c = vec3(0.0);
		col += c;
	}
	col /= float(spp);

	// progressive mean with an optional temporal window (uAccum2.y > 0): the history weight is capped,
	// so animated textures/lights blend in over ~window cooks instead of resetting to 1 sample.
	vec4 prev = texelFetch(sPrev, ivec2(pix), 0);
	float nPrev = (sampleIndex == 0u) ? 0.0 : prev.a;
	float nEff = nPrev;
	if (uAccum2.y > 0.0) nEff = min(nEff, uAccum2.y);
	vec3 acc = (nEff * prev.rgb + col) / (nEff + 1.0);
	Color[id] = vec4(acc, nPrev + 1.0);
}
