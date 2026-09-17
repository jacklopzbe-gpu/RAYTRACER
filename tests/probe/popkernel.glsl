// probe: per-point kernel writing Color; samples a TOP; cross-class read of vertex attribute from input 1; include test
#include "common_glsl"
void main()
{
	const uint id = TDIndex();
	if (id >= TDNumElements()) return;
	uint W = uint(uRes.x);
	uint x = id % W, y = id / W;
	vec4 s = texelFetch(sPrev, ivec2(int(x), int(y)), 0);
	vec3 vp = TDInVert_VP(1u, 4u, 0u);           // vertex 4 of input 1
	float pi = PI;                                // from common_glsl
	Color[id] = vec4(float(x) / uRes.x, float(y) / uRes.y, s.r + vp.x * 0.0 + pi * 0.0, float(id));
}
