// atlas_b.frag - adds the emit map (input 1) into the top-right quadrant of the atlas (input 0).
out vec4 fragColor;
void main()
{
	vec2 uv = vUV.st;
	vec2 q = floor(uv * 2.0);
	vec4 c = texture(sTD2DInputs[0], uv);
	if (q.x >= 1.0 && q.y >= 1.0) c = texture(sTD2DInputs[1], fract(uv * 2.0));
	fragColor = TDOutputSwizzle(c);
}
