// probe 2: vertex-class buffers (de-indexed). pixel x = vertex index.
out vec4 fragColor;
void main()
{
	uint i = uint(gl_FragCoord.x);
	if (gl_FragCoord.y < 1.0) fragColor = vec4(TDBuffer_VP(i), float(TDBufferLength_VP()));
	else fragColor = vec4(TDBuffer_VN(i), float(TDBufferLength_VN()));
}
