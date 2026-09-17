// env_default.frag - dark studio environment with drifting blue and orange light streaks (equirectangular).
uniform vec4 uTime;
out vec4 fragColor;

float hash(vec2 p)
{
	// integer hash (no precision loss for large coordinates)
	uvec2 q = uvec2(ivec2(floor(p)) + 32768);
	uint n = q.x * 1597334677u ^ q.y * 3812015801u;
	n = (n ^ (n >> 16u)) * 2246822519u; n ^= n >> 13u;
	return float(n) * (1.0 / 4294967296.0);
}
float noise(vec2 p)
{
	vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}

void main()
{
	vec2 uv = vUV.st;
	float t = uTime.x * 0.15;
	// long horizontal streaks: high frequency in v, low in u
	float s1 = noise(vec2(uv.x * 3.0 + t, uv.y * 40.0));
	float s2 = noise(vec2(uv.x * 5.0 - t * 0.7 + 7.0, uv.y * 25.0 + 3.0));
	float streakA = smoothstep(0.62, 0.9, s1);
	float streakB = smoothstep(0.68, 0.92, s2);
	vec3 blue = vec3(0.25, 0.55, 1.0) * 6.0;
	vec3 orange = vec3(1.0, 0.45, 0.15) * 4.0;
	vec3 col = blue * streakA + orange * streakB * 0.8;
	col += vec3(0.02, 0.03, 0.06);                                   // faint ambient
	col *= smoothstep(0.05, 0.3, uv.y) * 0.8 + 0.2;                  // darker below the horizon
	fragColor = TDOutputSwizzle(vec4(col, 1.0));
}
