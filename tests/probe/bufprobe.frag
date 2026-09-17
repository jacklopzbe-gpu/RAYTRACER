// probe: dump POP buffer contents into pixels. pixel x = element index.
out vec4 fragColor;
void main()
{
	uint i = uint(gl_FragCoord.x);
	uint n = TDBufferLength_P();
	vec3 p = TDBuffer_P(i);
	if (gl_FragCoord.y < 1.0) fragColor = vec4(p, float(n));
	else fragColor = vec4(TDBuffer_N(i), float(TDBufferLength_N()));
}
