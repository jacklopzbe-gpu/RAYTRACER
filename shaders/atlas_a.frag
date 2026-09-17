// atlas_a.frag - packs 3 material maps into a 2x2 atlas (GLSL TOP has only 3 inputs).
// input 0 = albedo -> bottom-left, input 1 = rough/metal -> bottom-right, input 2 = normal -> top-left.
out vec4 fragColor;
void main()
{
	vec2 uv = vUV.st;
	vec2 q = floor(uv * 2.0);
	vec2 luv = fract(uv * 2.0);
	vec4 c = vec4(0.0);
	if (q.y < 1.0 && q.x < 1.0) c = texture(sTD2DInputs[0], luv);
	else if (q.y < 1.0)         c = texture(sTD2DInputs[1], luv);
	else if (q.x < 1.0)         c = texture(sTD2DInputs[2], luv);
	fragColor = TDOutputSwizzle(c);
}
