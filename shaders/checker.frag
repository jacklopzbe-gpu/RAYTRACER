// checker.frag - test albedo texture (checkerboard) for the mesh material maps.
uniform vec4 uChecker;   // x = tiles, rgb of colors below
out vec4 fragColor;
void main()
{
	vec2 c = floor(vUV.st * uChecker.x);
	float k = mod(c.x + c.y, 2.0);
	vec3 col = mix(vec3(0.9, 0.9, 0.85), vec3(0.2, 0.25, 0.6), k);
	fragColor = TDOutputSwizzle(vec4(col, 1.0));
}
