# demo_ribbons.py - builds a chrome-ribbons demo scene with POPs and connects it to the ray tracer's in_mesh.
# Usage (Textport, after build_network.py):
#   exec(open('C:/Users/NORWAY_PC/Documents/RAYTRACER/td/demo_ribbons.py').read())
# Creates /project1/ribbons (Base COMP) whose output feeds /project1/rt (in_mesh) and sets the look parameters.
# Materials by point attribute 'mat': 0 = Mesh params, 1 = emissive (Color * Mesh Emit Intensity), 2 = glass (Color = tint), 3 = chrome.

PARENT = '/project1'
RT = '/project1/rt'

def _get(parent, optype, name):
	o = parent.op(name)
	return o if o is not None else parent.create(optype, name)

def _setvec(o, prefix, vals):
	pars = sorted([p for p in o.pars(prefix + '*') if p.name != prefix], key=lambda p: p.name)
	if not pars: pars = [getattr(o.par, prefix)]
	for p, v in zip(pars, vals): p.val = v

def _mat(parent, name, src, mat, col):
	at = _get(parent, attributePOP, name); at.inputConnectors[0].connect(src)
	at.par.attr0name = 'custom'; at.par.attr0customname = 'mat'; at.par.attr0type = 'float'; at.par.attr0numcomps = 1
	_setvec(at, 'attr0value', [float(mat)])
	at.par.attr1name = 'color'; _setvec(at, 'attr1value', list(col) + [1.0])
	return at

def build_ribbons():
	P = op(PARENT); rt = op(RT)
	base = _get(P, baseCOMP, 'ribbons'); base.nodeX, base.nodeY = rt.nodeX - 300, rt.nodeY
	# ribbons: long thin grid displaced by animated noise, copied 4 times
	grid = _get(base, gridPOP, 'rib_grid'); grid.par.surftype = 'quads'; grid.par.cols = 400; grid.par.rows = 6
	_setvec(grid, 'size', [10.0, 0.5, 1.0])
	nz = _get(base, noisePOP, 'rib_noise'); nz.inputConnectors[0].connect(grid)
	nz.par.amp = 1.6; nz.par.period = 3.0; nz.par.harmon = 2; nz.par.computenormals = True
	nz.par.t4d.expr = 'absTime.seconds * 0.3'
	cp = _get(base, copyPOP, 'rib_copy'); cp.inputConnectors[0].connect(nz); cp.par.ncy = 4
	_setvec(cp, 't', [0.0, 0.7, -0.8]); _setvec(cp, 'r', [15.0, 25.0, 30.0])
	parts = [_mat(base, 'rib_mat', cp, 3, (0.9, 0.9, 0.95))]
	def sphere(name, pos, rad, mat, col):
		sp = _get(base, spherePOP, name); sp.par.freq = 14
		for p in sp.pars('rad*'): p.val = rad
		sp.par.tx, sp.par.ty, sp.par.tz = pos
		return _mat(base, name + '_mat', sp, mat, col)
	parts += [sphere('emi_blue', (-2.5, 1.5, -1.0), 0.25, 1, (0.3, 0.6, 1.0)),
	          sphere('emi_orange', (2.2, 0.8, 0.5), 0.2, 1, (1.0, 0.5, 0.2)),
	          sphere('bubble1', (0.8, 0.9, 1.5), 0.45, 2, (0.85, 0.95, 1.0)),
	          sphere('bubble2', (-1.2, 0.2, 2.0), 0.3, 2, (0.9, 0.95, 1.0)),
	          sphere('bubble3', (1.9, 2.0, -0.5), 0.35, 2, (0.9, 0.9, 1.0))]
	mg = _get(base, mergePOP, 'scene_merge')
	for i, pp in enumerate(parts):
		if len(mg.inputs) <= i or mg.inputs[i] != pp:
			pp.outputConnectors[0].connect(mg)
	out = _get(base, outPOP, 'out1'); out.inputConnectors[0].connect(mg)
	for i, c in enumerate(base.children):
		c.nodeX, c.nodeY = (i % 4) * 160, -(i // 4) * 120
	# connect the component output to rt's in_mesh connector
	rt_in = [c for c in rt.inputConnectors if c.inOP and c.inOP.name == 'in_mesh'][0]
	if not any(o.owner == base for o in rt_in.connections):
		base.outputConnectors[0].connect(rt_in)
	# look
	cam = rt.op('cam1'); cam.par.tx = 0; cam.par.ty = 1.2; cam.par.tz = 9.0; cam.par.rx = -6; cam.par.ry = 0
	rt.par.Demoobjects = 0; rt.par.Useenvmap = 1; rt.par.Envint = 1.0; rt.par.Envvisible = 0
	rt.par.Floorcolorr = 0.03; rt.par.Floorcolorg = 0.03; rt.par.Floorcolorb = 0.04; rt.par.Floormetallic = 1.0; rt.par.Floorrough = 0.05
	rt.par.Lightint = 2.0; rt.par.Lightposy = 5.0; rt.par.Lightsizex = 3.0; rt.par.Lightsizey = 1.0
	rt.par.Meshemitint = 25.0; rt.par.Glassior = 1.4; rt.par.Glassabsorb = 0.3
	rt.par.Dispersion = 0.3; rt.par.Iridescence = 0.5; rt.par.Meshboundr = 100.0
	rt.par.Usealbedomap = 0; rt.par.Usenormalmap = 0
	rt.par.Resetongeometry = 1; rt.par.Spp = 4; rt.par.Window = 0
	return base

build_ribbons()
