# accum_ctl.py - Execute DAT (Frame Start) inside the 'rt' container.
# Keeps the progressive sample index in the container storage ('sample') and
# resets it to 0 whenever the camera, the light or any scene uniform changes.

def _signature(rt):
	cam = rt.op('cam1')
	g = rt.op('trace_pop')
	sig = [str(cam.worldTransform), cam.par.fov.eval()]
	if rt.par.Resetongeometry.eval():
		sig.append(rt.op('mesh_tri').totalCooks)          # geometry re-cooked -> reset (off: blend with the temporal window)
	if rt.par.Resetontexture.eval():
		sig.append(rt.op('maps_atlas').totalCooks)
	if rt.par.Offline.eval():
		sig.append(absTime.frame)                       # offline: every frame starts from scratch (Offlinespp samples)
	accum_par = rt.fetch('accum_par', 'vec4valuex')
	for p in g.pars('vec*value*'):
		if p.name != accum_par:
			sig.append(p.eval())
	return tuple(sig)

def _pushCamera(rt):
	"""GLSL POP uniforms are only re-uploaded when TD sees a parameter dependency; cam.worldTransform has none,
	so write the 4 columns of the camera matrix into the vec uniforms uCamC0..3 every frame."""
	g = rt.op('trace_pop'); cam = rt.op('cam1')
	m = cam.worldTransform
	base = rt.fetch('cam_vec_base', 17)
	for c in range(4):
		for r, comp in enumerate('xyzw'):
			p = getattr(g.par, 'vec%dvalue%s' % (base + c, comp))
			v = m[r, c]
			if p.val != v:
				p.val = v

def _updateInputs(rt):
	"""Flag which component inputs have something connected (switches read the flags from storage)."""
	for c in rt.inputConnectors:
		inop = c.inOP
		if inop is None:
			continue
		key = inop.name + '_on'
		val = 1 if len(c.connections) > 0 else 0
		if rt.fetch(key, None) != val:
			rt.store(key, val)

def _updateOffline(rt):
	want = not rt.par.Offline.eval()
	if project.realTime != want:
		project.realTime = want

def onFrameStart(frame):
	rt = me.parent()
	g = rt.op('trace_pop')
	_pushCamera(rt)
	_updateInputs(rt)
	_updateOffline(rt)
	sig = _signature(rt)
	cooks = g.totalCooks
	if sig != rt.fetch('sig', None) or rt.fetch('reset', False):
		rt.store('sig', sig)
		rt.store('sample', 0)
		rt.store('reset', False)
	elif cooks != rt.fetch('cooks', -1):
		# the kernel really ran since the last frame start -> next sample index
		rt.store('sample', rt.fetch('sample', 0) + 1)
	rt.store('cooks', cooks)
	# TOP/POP chains only cook when something pulls them; pull the output every frame so the
	# progressive accumulation advances even when no viewer shows it.
	if rt.par.Alwayscook.eval():
		rt.op('out_final').cook()
	return
