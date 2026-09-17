// common.glsl - shared helpers for the path tracer (TouchDesigner GLSL TOP, GLSL 4.60)
#ifndef RT_COMMON_GLSL
#define RT_COMMON_GLSL

#define PI      3.14159265358979323846
#define INV_PI  0.31830988618379067154
#define EPS     1e-4
#define INF     1e30

struct Ray {
	vec3 o;   // origin (world)
	vec3 d;   // direction (world, normalized)
};

// Camera ray for a pixel.
//   uv        : [0,1]^2 pixel center (vUV)
//   camToWorld: Camera COMP worldTransform (camera looks down -Z, +Y up)
//   fovDeg    : horizontal field of view in degrees (Camera COMP 'fov', default Viewing Angle Method)
//   aspect    : width / height of the output
Ray cameraRay(vec2 uv, mat4 camToWorld, float fovDeg, float aspect)
{
	vec2 ndc = uv * 2.0 - 1.0;
	float tanHalf = tan(radians(fovDeg) * 0.5);
	vec3 dCam = normalize(vec3(ndc.x * tanHalf, ndc.y * tanHalf / aspect, -1.0));
	Ray r;
	r.o = (camToWorld * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	r.d = normalize((camToWorld * vec4(dCam, 0.0)).xyz);
	return r;
}

// ---------------------------------------------------------------- geometry
struct Hit {
	float t;      // ray parameter (INF if none)
	vec3  p;      // hit position (world)
	vec3  n;      // geometric normal, facing against the ray
	int   mat;    // material id (-1 = none)
	bool  inside; // true when the ray hit the surface from inside (geometric normal was flipped)
	int   prim;   // triangle index for meshes (-1 otherwise)
	vec2  bary;   // barycentrics (u, v) of the triangle hit: p = (1-u-v)*A + u*B + v*C
	vec3  ns;     // shading normal (interpolated / normal-mapped), same side as n
	vec2  uv;     // texture coordinate
	vec3  tg;     // tangent (for normal mapping), zero if unknown
	int   matId;  // mesh per-vertex material id
	vec4  vcol;   // mesh per-vertex color
};

Hit noHit() { Hit h; h.t = INF; h.p = vec3(0.0); h.n = vec3(0.0, 1.0, 0.0); h.mat = -1; h.inside = false; h.prim = -1; h.bary = vec2(0.0); h.ns = h.n; h.uv = vec2(0.0); h.tg = vec3(0.0); h.matId = 0; h.vcol = vec4(1.0); return h; }

// Infinite plane through 'p0' with unit normal 'n'.
bool hitPlane(Ray r, vec3 p0, vec3 n, float tMax, inout Hit h, int mat)
{
	float denom = dot(n, r.d);
	if (abs(denom) < 1e-6) return false;
	float t = dot(p0 - r.o, n) / denom;
	if (t <= EPS || t >= tMax || t >= h.t) return false;
	h.t = t; h.p = r.o + r.d * t; h.n = denom < 0.0 ? n : -n; h.inside = denom > 0.0; h.mat = mat; h.ns = h.n; h.uv = h.p.xz; h.tg = vec3(0.0);
	return true;
}

// Sphere with center c and radius rad. Robust quadratic (no catastrophic cancellation).
bool hitSphere(Ray r, vec3 c, float rad, float tMax, inout Hit h, int mat)
{
	vec3 oc = r.o - c;
	float b = dot(oc, r.d);
	float cc = dot(oc, oc) - rad * rad;
	float disc = b * b - cc;
	if (disc < 0.0) return false;
	float s = sqrt(disc);
	float q = (b < 0.0) ? -b + s : -b - s;   // q = -(b + sign(b)*s)
	float t0 = q;                             // one root
	float t1 = (q != 0.0) ? cc / q : INF;     // other root, via product of roots
	float tn = min(t0, t1), tf = max(t0, t1);
	float t = tn > EPS ? tn : tf;
	if (t <= EPS || t >= tMax || t >= h.t) return false;
	h.t = t; h.p = r.o + r.d * t;
	vec3 n = (h.p - c) / rad;
	h.inside = dot(n, r.d) > 0.0;
	h.n = h.inside ? -n : n;
	h.mat = mat; h.ns = h.n; h.tg = vec3(0.0);
	h.uv = vec2(atan(n.z, n.x) * (0.5 * INV_PI) + 0.5, acos(clamp(n.y, -1.0, 1.0)) * INV_PI);
	return true;
}

// Axis-aligned box [bmin, bmax] (slab test).
bool hitBox(Ray r, vec3 bmin, vec3 bmax, float tMax, inout Hit h, int mat)
{
	vec3 invD = 1.0 / r.d;                      // IEEE: division by 0 -> inf, handled by min/max
	vec3 t0s = (bmin - r.o) * invD;
	vec3 t1s = (bmax - r.o) * invD;
	vec3 tsm = min(t0s, t1s), tbg = max(t0s, t1s);
	float tn = max(max(tsm.x, tsm.y), tsm.z);
	float tf = min(min(tbg.x, tbg.y), tbg.z);
	if (tf < tn || tf <= EPS) return false;
	float t = tn > EPS ? tn : tf;
	if (t >= tMax || t >= h.t) return false;
	h.t = t; h.p = r.o + r.d * t;
	// normal: dominant axis of the hit point in the box's local frame
	vec3 c = 0.5 * (bmin + bmax), e = 0.5 * (bmax - bmin);
	vec3 q = (h.p - c) / e; vec3 a = abs(q);
	vec3 n = (a.x > a.y && a.x > a.z) ? vec3(sign(q.x), 0.0, 0.0)
	       : (a.y > a.z ? vec3(0.0, sign(q.y), 0.0) : vec3(0.0, 0.0, sign(q.z)));
	n = normalize(n);
	h.inside = dot(n, r.d) > 0.0;
	h.n = h.inside ? -n : n;
	h.mat = mat; h.ns = h.n; h.uv = q.xy; h.tg = vec3(0.0);
	return true;
}

// Moller-Trumbore ray/triangle. Two-sided. Writes t/bary only (caller fills the rest).
bool hitTriangle(Ray r, vec3 a, vec3 b, vec3 c, float tMax, inout float tBest, out vec2 bary)
{
	vec3 e1 = b - a, e2 = c - a;
	vec3 pv = cross(r.d, e2);
	float det = dot(e1, pv);
	if (abs(det) < 1e-9) return false;
	float invDet = 1.0 / det;
	vec3 tv = r.o - a;
	float u = dot(tv, pv) * invDet;
	if (u < 0.0 || u > 1.0) return false;
	vec3 qv = cross(tv, e1);
	float v = dot(r.d, qv) * invDet;
	if (v < 0.0 || u + v > 1.0) return false;
	float t = dot(e2, qv) * invDet;
	if (t <= EPS || t >= tMax || t >= tBest) return false;
	tBest = t; bary = vec2(u, v);
	return true;
}

// Ray vs bounding sphere (early-out test only)
bool intersectsSphere(Ray r, vec3 c, float rad)
{
	vec3 oc = r.o - c;
	float b = dot(oc, r.d);
	float cc = dot(oc, oc) - rad * rad;
	if (cc <= 0.0) return true;          // origin inside
	if (b > 0.0) return false;           // sphere behind
	return b * b - cc >= 0.0;
}

// ---------------------------------------------------------------- random numbers
// PCG-style hash. State advances per call.
uint rngState;

uint pcgHash(uint v)
{
	uint state = v * 747796405u + 2891336453u;
	uint word = ((state >> ((state >> 28u) + 4u)) ^ state) * 277803737u;
	return (word >> 22u) ^ word;
}

void rngSeed(uvec2 pixel, uint frame)
{
	rngState = pcgHash(pixel.x + 1973u * pixel.y + 9277u * frame + 26699u);
}

// Uniform float in [0,1)
float rand()
{
	rngState = pcgHash(rngState);
	return float(rngState) * (1.0 / 4294967296.0);
}
vec2 rand2() { return vec2(rand(), rand()); }

// Orthonormal basis from a unit normal (Duff et al. 2017)
void basis(vec3 n, out vec3 t, out vec3 b)
{
	float s = n.z >= 0.0 ? 1.0 : -1.0;
	float a = -1.0 / (s + n.z);
	float c = n.x * n.y * a;
	t = vec3(1.0 + s * n.x * n.x * a, s * c, -s * n.x);
	b = vec3(c, s + n.y * n.y * a, -n.y);
}

// Cosine-weighted direction around n. pdf = cos(theta)/PI
vec3 sampleCosineHemisphere(vec3 n, vec2 xi)
{
	float r = sqrt(xi.x);
	float phi = 2.0 * PI * xi.y;
	vec3 t, b; basis(n, t, b);
	float x = r * cos(phi), y = r * sin(phi);
	float z = sqrt(max(0.0, 1.0 - xi.x));
	return normalize(t * x + b * y + n * z);
}

// ---------------------------------------------------------------- lights & materials
// Rectangular area light: center c, half-extents along u/v (unit vectors), normal n = cross(u,v).
struct RectLight {
	vec3 c;       // center
	vec3 u, v;    // unit edge directions
	vec2 hsize;   // half sizes along u and v
	vec3 n;       // emitting side normal
	vec3 L;       // radiance (color * intensity)
};

float rectLightArea(RectLight l) { return 4.0 * l.hsize.x * l.hsize.y; }

// Point on the light for a uniform sample xi in [0,1]^2.
vec3 rectLightPoint(RectLight l, vec2 xi)
{
	vec2 s = (xi * 2.0 - 1.0) * l.hsize;
	return l.c + l.u * s.x + l.v * s.y;
}

struct Material {
	vec3  albedo;
	vec3  emit;
	float metallic;
	float roughness;
	float transmission;   // 1 = smooth dielectric
	float ior;
	vec3  absorb;         // Beer-Lambert absorption coefficient inside the medium (per unit length)
};

// ---------------------------------------------------------------- BSDF (GGX + Lambert)
float luminance(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

vec3 fresnelSchlick(vec3 F0, float cosTheta)
{
	float f = pow(1.0 - clamp(cosTheta, 0.0, 1.0), 5.0);
	return F0 + (1.0 - F0) * f;
}

// GGX / Trowbridge-Reitz NDF, alpha = roughness^2
float ggxD(float NdotH, float a)
{
	float a2 = a * a;
	float d = NdotH * NdotH * (a2 - 1.0) + 1.0;
	return a2 / (PI * d * d);
}

// Smith height-correlated masking-shadowing (Heitz 2014), returns G2
float ggxG2(float NdotV, float NdotL, float a)
{
	float a2 = a * a;
	float gv = NdotL * sqrt(NdotV * NdotV * (1.0 - a2) + a2);
	float gl = NdotV * sqrt(NdotL * NdotL * (1.0 - a2) + a2);
	return 2.0 * NdotL * NdotV / max(gv + gl, 1e-7);
}

float ggxG1(float NdotV, float a)
{
	float a2 = a * a;
	return 2.0 * NdotV / (NdotV + sqrt(a2 + (1.0 - a2) * NdotV * NdotV));
}

// Sample a visible normal (Heitz 2018), wo in tangent space (z = normal).
vec3 sampleGGXVNDF(vec3 wo, float a, vec2 xi)
{
	vec3 Vh = normalize(vec3(a * wo.x, a * wo.y, wo.z));
	float lensq = Vh.x * Vh.x + Vh.y * Vh.y;
	vec3 T1 = lensq > 0.0 ? vec3(-Vh.y, Vh.x, 0.0) / sqrt(lensq) : vec3(1.0, 0.0, 0.0);
	vec3 T2 = cross(Vh, T1);
	float r = sqrt(xi.x);
	float phi = 2.0 * PI * xi.y;
	float t1 = r * cos(phi);
	float t2 = r * sin(phi);
	float sc = 0.5 * (1.0 + Vh.z);
	t2 = (1.0 - sc) * sqrt(max(0.0, 1.0 - t1 * t1)) + sc * t2;
	vec3 Nh = t1 * T1 + t2 * T2 + sqrt(max(0.0, 1.0 - t1 * t1 - t2 * t2)) * Vh;
	return normalize(vec3(a * Nh.x, a * Nh.y, max(0.0, Nh.z)));
}

float matAlpha(Material m) { float r = clamp(m.roughness, 0.02, 1.0); return r * r; }
vec3  matF0(Material m)    { return mix(vec3(0.04), m.albedo, m.metallic); }

// Probability of picking the specular lobe
float specProb(Material m, vec3 n, vec3 wo)
{
	vec3 F = fresnelSchlick(matF0(m), max(dot(n, wo), 0.0));
	float ps = luminance(F);
	float pd = (1.0 - m.metallic) * luminance(m.albedo);
	return clamp(ps / max(ps + pd, 1e-4), 0.05, 0.95);
}

// Evaluate f(wo,wi) * |cos| and the combined pdf for the opaque (reflective) material.
vec3 bsdfEval(Material m, vec3 n, vec3 wo, vec3 wi, out float pdf)
{
	float NdotL = dot(n, wi), NdotV = dot(n, wo);
	pdf = 0.0;
	if (NdotL <= 0.0 || NdotV <= 0.0) return vec3(0.0);
	vec3 h = normalize(wo + wi);
	float NdotH = max(dot(n, h), 0.0), VdotH = max(dot(wo, h), 0.0);
	float a = matAlpha(m);
	vec3 F = fresnelSchlick(matF0(m), VdotH);
	float D = ggxD(NdotH, a);
	float G = ggxG2(NdotV, NdotL, a);
	vec3 fs = F * D * G / max(4.0 * NdotV * NdotL, 1e-7);
	vec3 fd = (1.0 - m.metallic) * (1.0 - F) * m.albedo * INV_PI;
	float ps = specProb(m, n, wo);
	float pdfSpec = D * ggxG1(NdotV, a) / max(4.0 * NdotV, 1e-7);   // VNDF pdf
	float pdfDiff = NdotL * INV_PI;
	pdf = ps * pdfSpec + (1.0 - ps) * pdfDiff;
	return (fs + fd) * NdotL;
}

// Sample wi; returns f*cos/pdf as weight. pdf written out for MIS.
vec3 bsdfSample(Material m, vec3 n, vec3 wo, vec3 xi, out vec3 wi, out float pdf)
{
	float ps = specProb(m, n, wo);
	if (xi.z < ps) {
		vec3 t, b; basis(n, t, b);
		vec3 woT = vec3(dot(wo, t), dot(wo, b), dot(wo, n));
		vec3 hT = sampleGGXVNDF(woT, matAlpha(m), xi.xy);
		vec3 h = normalize(t * hT.x + b * hT.y + n * hT.z);
		wi = reflect(-wo, h);
	} else {
		wi = sampleCosineHemisphere(n, xi.xy);
	}
	vec3 f = bsdfEval(m, n, wo, wi, pdf);
	if (pdf <= 0.0) return vec3(0.0);
	return f / pdf;
}

#endif // RT_COMMON_GLSL
