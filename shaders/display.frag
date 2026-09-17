// display.frag - exposure + tonemap + linear->sRGB for viewing the accumulation buffer.
// Input 0: accumulation (rgb linear mean, a = sample count).
uniform vec4 uDisplay;   // x = exposure (multiplier), y = tonemap (0 = clamp, 1 = ACES), z = show sample count (0/1)

out vec4 fragColor;

vec3 acesFilm(vec3 x)
{
	const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
	return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

vec3 linearToSRGB(vec3 c)
{
	c = clamp(c, 0.0, 1.0);
	return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}

void main()
{
	vec4 acc = texture(sTD2DInputs[0], vUV.st);
	vec3 c = acc.rgb * uDisplay.x;
	if (uDisplay.y > 0.5) c = acesFilm(c);
	c = linearToSRGB(c);
	if (uDisplay.z > 0.5) c = vec3(fract(acc.a / 64.0));
	fragColor = TDOutputSwizzle(vec4(c, 1.0));
}
