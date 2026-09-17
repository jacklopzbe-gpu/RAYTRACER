// probe: hardware ray query inside a GLSL POP against the Collision POP (uAS)
void main()
{
	const uint id = TDIndex();
	if (id >= TDNumElements()) return;
	vec3 o = vec3(float(id) * 0.02 - 0.4, 0.0, -5.0);
	vec3 d = vec3(0.0, 0.0, 1.0);
	rayQueryEXT rq;
	rayQueryInitializeEXT(rq, uAS, gl_RayFlagsOpaqueEXT, 0xFF, o, 0.001, d, 100.0);
	while (rayQueryProceedEXT(rq)) { }
	float t = -1.0, prim = -1.0, front = 0.0;
	if (rayQueryGetIntersectionTypeEXT(rq, true) == gl_RayQueryCommittedIntersectionTriangleEXT) {
		t = rayQueryGetIntersectionTEXT(rq, true);
		prim = float(rayQueryGetIntersectionPrimitiveIndexEXT(rq, true));
		front = rayQueryGetIntersectionFrontFaceEXT(rq, true) ? 1.0 : 0.0;
	}
	P[id] = vec3(t, prim, front);
}
