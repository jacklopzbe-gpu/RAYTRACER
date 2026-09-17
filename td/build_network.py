# build_network.py — builds (or refreshes) the ray tracer network inside TouchDesigner.
# Usage inside TD (Textport):  exec(open('C:/Users/NORWAY_PC/Documents/RAYTRACER/td/build_network.py').read())
# Idempotent: existing operators are reused, parameters are re-applied.
import os

def _detect_root():
	"""Repo root: RT_ROOT env var, the .toe folder, or its parent (tools/RayTest.toe)."""
	cands = [os.environ.get('RT_ROOT'), project.folder, os.path.dirname(project.folder)]
	for c in cands:
		if c and os.path.exists(os.path.join(c, 'shaders', 'common.glsl')):
			return c.replace('\\', '/')
	raise RuntimeError('RAYTRACER repo not found: save the .toe in the repo root or set the RT_ROOT environment variable')

ROOT = _detect_root()
# when the .toe is saved in the repo root, store paths relative to the project so the .toe is portable
REL = os.path.normcase(os.path.abspath(ROOT)) == os.path.normcase(os.path.abspath(project.folder))
SHADERS = 'shaders' if REL else ROOT + '/shaders'
TDDIR = 'td' if REL else ROOT + '/td'
RENDERS = 'renders' if REL else ROOT + '/renders'
PARENT = '/project1'
NAME = 'rt'

def get_or_create(parent, optype, name):
	o = parent.op(name)
	if o is None:
		o = parent.create(optype, name)
	return o

def _page(comp, name):
	for pg in comp.customPages:
		if pg.name == name:
			return pg
	return comp.appendCustomPage(name)

def _par(page, kind, name, label, default, minv=None, maxv=None, nmin=None, nmax=None):
	comp = page.owner
	created = False
	if not hasattr(comp.par, name if kind in ('Int', 'Float', 'Toggle') else name + {'XYZ': 'x', 'XY': 'x', 'RGB': 'r'}[kind]):
		getattr(page, 'append' + kind)(name, label=label)
		created = True
	pars = [p for p in comp.customPars if p.name == name or (p.name.startswith(name) and p.name[len(name):] in ('x', 'y', 'z', 'r', 'g', 'b'))]
	order = {'x': 0, 'y': 1, 'z': 2, 'w': 3, 'r': 0, 'g': 1, 'b': 2, 'a': 3}
	pars.sort(key=lambda p: order.get(p.name[len(name):], 0) if p.name != name else 0)
	if not isinstance(default, (list, tuple)):
		default = [default]
	for p, d in zip(pars, default):
		p.default = d
		if created:
			p.val = d
		if minv is not None: p.min = minv; p.clampMin = True
		if maxv is not None: p.max = maxv; p.clampMax = True
		if nmin is not None: p.normMin = nmin
		if nmax is not None: p.normMax = nmax
	return pars

def build_custom_pars(rt):
	"""Custom parameters that drive every uniform (Tarea 10)."""
	pg = _page(rt, 'Render')
	_par(pg, 'Int',    'Bounces',   'Max Bounces',        4, 0, 16)
	_par(pg, 'Float',  'Clamp',     'Radiance Clamp',     20.0, 0.0, None, 0.0, 50.0)
	_par(pg, 'Toggle', 'Nee',       'Next Event Estimation', 1)
	_par(pg, 'Float',  'Exposure',  'Exposure',           1.0, 0.0, None, 0.0, 4.0)
	_par(pg, 'Toggle', 'Tonemap',   'ACES Tonemap',       1)
	_par(pg, 'Toggle', 'Showsamples', 'Show Sample Count', 0)
	_par(pg, 'Int',    'Resw',      'Resolution W',       1280, 8, 8192)
	_par(pg, 'Int',    'Resh',      'Resolution H',       720, 8, 8192)
	_par(pg, 'Toggle', 'Denoise',   'Nvidia Denoise (needs NVIDIA Video Effects SDK)', 0)
	_par(pg, 'Toggle', 'Alwayscook', 'Always Cook (advance samples without a viewer)', 1)
	_par(pg, 'Int',    'Spp',       'Samples per Frame (live)', 1, 1, 64)
	_par(pg, 'Int',    'Window',    'Temporal Window (0 = accumulate forever)', 64, 0, 4096)
	_par(pg, 'Toggle', 'Resetontexture', 'Reset When Textures Change', 0)
	_par(pg, 'Toggle', 'Resetongeometry', 'Reset When Geometry Changes', 1)

	pg = _page(rt, 'Offline')
	_par(pg, 'Toggle', 'Offline',    'Offline Mode (realtime off, reset every frame)', 0)
	_par(pg, 'Int',    'Offlinespp', 'Offline Samples per Frame', 64, 1, 4096)
	_par(pg, 'Toggle', 'Record',     'Record (Movie File Out)', 0)
	_par(pg, 'Float',  'Denoisestrength', 'Denoise Strength', 1.0, 0.0, 1.0)

	pg = _page(rt, 'Glassfx')
	_par(pg, 'Float',  'Dispersion',   'Dispersion',        0.5, 0.0, None, 0.0, 2.0)
	_par(pg, 'Float',  'Iridescence',  'Iridescence',       0.6, 0.0, 1.0)
	_par(pg, 'Float',  'Iridscale',    'Iridescence Scale', 2.0, 0.0, None, 0.0, 8.0)
	_par(pg, 'Toggle', 'Tintedshadows', 'Tinted Shadows Through Glass', 1)
	if not hasattr(rt.par, 'Offlinefile'):
		pg = _page(rt, 'Offline'); pg.appendStr('Offlinefile', label='Output File')
		rt.par.Offlinefile = RENDERS + '/raytracer'

	pg = _page(rt, 'Light')
	_par(pg, 'XYZ',    'Lightpos',  'Rect Light Position', (1.5, 4.0, 2.0), None, None, -10.0, 10.0)
	_par(pg, 'XY',     'Lightsize', 'Rect Light Half Size', (1.0, 1.0), 0.01, None, 0.0, 5.0)
	_par(pg, 'RGB',    'Lightcolor', 'Rect Light Color',  (1.0, 0.95, 0.9))
	_par(pg, 'Float',  'Lightint',  'Rect Light Intensity', 12.0, 0.0, None, 0.0, 50.0)
	_par(pg, 'RGB',    'Emitcolor', 'Emissive Sphere Color', (1.0, 0.6, 0.2))
	_par(pg, 'Float',  'Emitint',   'Emissive Sphere Intensity', 30.0, 0.0, None, 0.0, 100.0)
	_par(pg, 'RGB',    'Envcolor',  'Sky Color',          (0.5, 0.6, 0.8))
	_par(pg, 'Float',  'Envint',    'Sky Intensity',      0.6, 0.0, None, 0.0, 5.0)
	_par(pg, 'Toggle', 'Useenvmap', 'Use Environment Map (in_env or env_default)', 0)
	_par(pg, 'Toggle', 'Envvisible', 'Environment Visible to Camera', 1)
	_par(pg, 'Float',  'Envrotate',  'Environment Rotation (deg)', 0.0, None, None, -180.0, 180.0)

	pg = _page(rt, 'Scene')
	_par(pg, 'Toggle', 'Floor',     'Floor', 1)
	_par(pg, 'Float',  'Floorheight', 'Floor Height', -1.0, None, None, -5.0, 5.0)
	_par(pg, 'RGB',    'Floorcolor', 'Floor Color', (0.7, 0.7, 0.7))
	_par(pg, 'Float',  'Floormetallic', 'Floor Metallic', 0.0, 0.0, 1.0)
	_par(pg, 'Float',  'Floorrough', 'Floor Roughness', 0.5, 0.0, 1.0)
	_par(pg, 'Toggle', 'Demoobjects', 'Demo Objects (spheres, box)', 1)

	pg = _page(rt, 'Materials')
	_par(pg, 'Float',  'Metalmetallic', 'Metal Sphere Metallic', 1.0, 0.0, 1.0)
	_par(pg, 'Float',  'Metalrough',    'Metal Sphere Roughness', 0.1, 0.0, 1.0)
	_par(pg, 'Float',  'Boxmetallic',   'Box Metallic',    0.0, 0.0, 1.0)
	_par(pg, 'Float',  'Boxrough',      'Box Roughness',   0.5, 0.0, 1.0)
	_par(pg, 'Float',  'Glassior',      'Glass IOR',       1.5, 1.0, 3.0)
	_par(pg, 'Float',  'Glassabsorb',   'Glass Absorption', 1.0, 0.0, None, 0.0, 5.0)
	_par(pg, 'RGB',    'Meshcolor',     'Mesh Color',      (0.85, 0.7, 0.3))
	_par(pg, 'Float',  'Meshmetallic',  'Mesh Metallic',   0.0, 0.0, 1.0)
	_par(pg, 'Float',  'Meshrough',     'Mesh Roughness',  0.4, 0.0, 1.0)

	pg = _page(rt, 'Mesh')
	_par(pg, 'XYZ',    'Meshboundc',    'Mesh Bound Center', (3.2, -0.3, 1.5), None, None, -10.0, 10.0)
	_par(pg, 'Float',  'Meshboundr',    'Mesh Bound Radius', 0.75, 0.0, None, 0.0, 10.0)
	_par(pg, 'Toggle', 'Usealbedomap', 'Use Albedo Map (input 1)', 1)
	_par(pg, 'Toggle', 'Usermmap',     'Use Rough/Metal Map (input 2)', 0)
	_par(pg, 'Toggle', 'Usenormalmap', 'Use Normal Map (input 3)', 1)
	_par(pg, 'Toggle', 'Useemitmap',   'Use Emit Map (input 4)', 0)
	_par(pg, 'Float',  'Normalstrength', 'Normal Map Strength', 1.0, 0.0, None, 0.0, 3.0)
	_par(pg, 'Float',  'Meshemitint',  'Mesh Emit Intensity', 5.0, 0.0, None, 0.0, 50.0)
	_par(pg, 'Float',  'Uvtiling',     'UV Tiling', 1.0, 0.0, None, 0.0, 16.0)

def build():
	parent = op(PARENT)
	rt = get_or_create(parent, containerCOMP, NAME)
	rt.par.w = 1280
	rt.par.h = 720
	build_custom_pars(rt)

	# --- shader sources synced to disk (Text DATs) ---
	common = get_or_create(rt, textDAT, 'common_glsl')
	common.par.file = SHADERS + '/common.glsl'
	common.par.syncfile = True
	common.par.loadonstartpulse.pulse()
	common.nodeX, common.nodeY = -400, 200

	trace_src = get_or_create(rt, textDAT, 'trace_frag')
	trace_src.par.file = SHADERS + '/trace.frag'
	trace_src.par.syncfile = True
	trace_src.par.loadonstartpulse.pulse()
	trace_src.nodeX, trace_src.nodeY = -400, 50

	# --- camera (the TD camera drives the rays) ---
	cam = get_or_create(rt, cameraCOMP, 'cam1')
	cam.nodeX, cam.nodeY = -400, -150

	# --- kernel: GLSL POP (hardware RT). One point per pixel. ---
	trace_src = get_or_create(rt, textDAT, 'trace_glsl')
	trace_src.par.file = SHADERS + '/trace.glsl'
	trace_src.par.syncfile = True
	trace_src.par.loadonstartpulse.pulse()
	trace_src.nodeX, trace_src.nodeY = -400, 50
	# legacy GLSL TOP kernel (Tareas 1-12) is removed if present
	for legacy in ('trace', 'trace_frag'):
		if rt.op(legacy) is not None: rt.op(legacy).destroy()

	grid = get_or_create(rt, gridPOP, 'pix_grid')
	grid.par.surftype = 'none'
	grid.par.cols.expr = 'parent().par.Resw'
	grid.par.rows.expr = 'parent().par.Resh'
	grid.nodeX, grid.nodeY = -200, 0

	glsl = get_or_create(rt, glslPOP, 'trace_pop')
	glsl.inputConnectors[0].connect(grid)
	glsl.par.computedat = trace_src
	glsl.par.attr0name = 'color'          # creates the 'Color' output attribute
	glsl.par.outputattrs = 'Color'
	glsl.par.asname = 'uAS'
	glsl.par.buildflag = 'fastbuild'      # geometry may animate
	glsl.nodeX, glsl.nodeY = 0, 0

	def vec(i, name, exprs=None, vals=None):
		setattr(glsl.par, 'vec%dname' % i, name)
		setattr(glsl.par, 'vec%dtype' % i, 'vec4')
		for k, comp in enumerate('xyzw'):
			par = getattr(glsl.par, 'vec%dvalue%s' % (i, comp))
			if exprs and k < len(exprs) and exprs[k] is not None: par.expr = exprs[k]
			elif vals and k < len(vals) and vals[k] is not None: par.expr = ''; par.val = vals[k]
	# camera matrix as 4 column vectors: matrix uniforms on GLSL POPs do not refresh when the camera moves
	glsl.par.matrix0name = ''
	glsl.par.matrix0value.expr = ''
	for c in range(4):
		vec(17 + c, 'uCamC%d' % c, vals=[1.0 if r == c else 0.0 for r in range(4)])   # written every frame by accum_ctl
	rt.store('cam_vec_base', 17)
	vec(0,  'uCamParams', ["op('cam1').par.fov"])
	vec(1,  'uLightPos',  ['parent().par.Lightposx', 'parent().par.Lightposy', 'parent().par.Lightposz'])
	vec(2,  'uLightSize', ['parent().par.Lightsizex', 'parent().par.Lightsizey'])
	vec(3,  'uLightColor', ['parent().par.Lightcolorr', 'parent().par.Lightcolorg', 'parent().par.Lightcolorb', 'parent().par.Lightint'])
	vec(4,  'uAccum', ["parent().fetch('sample', 0)", 'parent().par.Bounces', 'parent().par.Clamp', 'parent().par.Nee'])
	rt.store('accum_par', 'vec4valuex')
	vec(5,  'uEnv', ['parent().par.Envcolorr', 'parent().par.Envcolorg', 'parent().par.Envcolorb', 'parent().par.Envint'])
	vec(6,  'uMat2', ['parent().par.Metalmetallic', 'parent().par.Metalrough'])
	vec(7,  'uMat3', ['parent().par.Boxmetallic', 'parent().par.Boxrough'])
	vec(8,  'uMat4', ['parent().par.Glassior', 'parent().par.Glassabsorb'])
	vec(9,  'uEmit', ['parent().par.Emitcolorr', 'parent().par.Emitcolorg', 'parent().par.Emitcolorb', 'parent().par.Emitint'])
	vec(10, 'uMeshBound', ['parent().par.Meshboundcx', 'parent().par.Meshboundcy', 'parent().par.Meshboundcz', 'parent().par.Meshboundr'])
	vec(11, 'uMeshMat', ['parent().par.Meshmetallic', 'parent().par.Meshrough'])
	vec(12, 'uMeshColor', ['parent().par.Meshcolorr', 'parent().par.Meshcolorg', 'parent().par.Meshcolorb'])
	vec(13, 'uMeshMaps', ['parent().par.Usealbedomap', 'parent().par.Usermmap', 'parent().par.Usenormalmap', 'parent().par.Useemitmap'])
	vec(14, 'uMeshMapParams', ['parent().par.Normalstrength', 'parent().par.Meshemitint', 'parent().par.Uvtiling'])
	vec(15, 'uRes', ['parent().par.Resw', 'parent().par.Resh'])
	vec(16, 'uGlassFx', ['parent().par.Dispersion', 'parent().par.Iridescence', 'parent().par.Iridscale', 'parent().par.Tintedshadows'])
	vec(21, 'uAccum2', ['parent().par.Offlinespp if parent().par.Offline else parent().par.Spp', 'parent().par.Window'])
	vec(22, 'uScene', ['parent().par.Floor', 'parent().par.Floorheight', 'parent().par.Demoobjects', 'parent().par.Useenvmap'])
	vec(23, 'uFloor', ['parent().par.Floorcolorr', 'parent().par.Floorcolorg', 'parent().par.Floorcolorb'])
	vec(24, 'uFloorMat', ['parent().par.Floormetallic', 'parent().par.Floorrough'])
	vec(25, 'uEnv2', ['parent().par.Envvisible', 'parent().par.Envrotate'])

	# --- progressive accumulation loop: black -> fb -> (sampler sPrev of trace_pop) -> acc (POP to TOP) ; fb.target = acc ---
	black = get_or_create(rt, constantTOP, 'black')
	black.par.colorr = 0; black.par.colorg = 0; black.par.colorb = 0; black.par.alpha = 0
	black.par.outputresolution = 'custom'; black.par.resolutionw.expr = 'parent().par.Resw'; black.par.resolutionh.expr = 'parent().par.Resh'
	black.par.format = 'rgba32float'
	black.nodeX, black.nodeY = -400, -300
	fb = get_or_create(rt, feedbackTOP, 'fb')
	fb.inputConnectors[0].connect(black)
	fb.par.format = 'rgba32float'
	fb.nodeX, fb.nodeY = -200, -300
	if rt.op('acc') is not None and rt.op('acc').type != 'popto':
		rt.op('acc').destroy()
	acc = get_or_create(rt, poptoTOP, 'acc')
	acc.par.pop = glsl
	acc.par.rgbamode = 'custom'; acc.par.attribscope = 'Color'; acc.par.layout = 'popdim'; acc.par.format = 'rgba32float'
	acc.nodeX, acc.nodeY = 300, 0
	fb.par.top = acc
	glsl.par.sampler0name = 'sPrev'; glsl.par.sampler0top = fb

	# frame-start controller (sample counter + auto reset)
	ctl = get_or_create(rt, executeDAT, 'accum_ctl')
	ctl.par.file = TDDIR + '/accum_ctl.py'
	ctl.par.syncfile = True
	ctl.par.loadonstartpulse.pulse()
	ctl.par.framestart = True
	ctl.nodeX, ctl.nodeY = -400, -450

	# --- display (exposure + tonemap + sRGB) -> denoise -> out ---
	disp_src = get_or_create(rt, textDAT, 'display_frag')
	disp_src.par.file = SHADERS + '/display.frag'
	disp_src.par.syncfile = True
	disp_src.par.loadonstartpulse.pulse()
	disp_src.nodeX, disp_src.nodeY = -400, 350
	disp = get_or_create(rt, glslTOP, 'display')
	disp.par.pixeldat = disp_src
	disp.inputConnectors[0].connect(acc)
	disp.par.format = 'rgba8fixed'
	disp.par.vec0name = 'uDisplay'
	disp.par.vec0valuex.expr = 'parent().par.Exposure'; disp.par.vec0valuey.expr = 'parent().par.Tonemap'; disp.par.vec0valuez.expr = 'parent().par.Showsamples'
	disp.nodeX, disp.nodeY = 500, 0
	dn = get_or_create(rt, nvidiadenoiseTOP, 'denoise')
	dn.inputConnectors[0].connect(disp)
	dn.par.strength.expr = 'parent().par.Denoisestrength'
	dn.nodeX, dn.nodeY = 700, 0
	sw = get_or_create(rt, switchTOP, 'denoise_switch')
	sw.inputConnectors[0].connect(disp); sw.inputConnectors[1].connect(dn)
	sw.par.index.expr = 'int(parent().par.Denoise)'
	sw.nodeX, sw.nodeY = 800, -100

	# --- mesh source (Tarea 11): swap the input of mesh_in for any POP; triangulated + de-indexed downstream
	src_pop = get_or_create(rt, spherePOP, 'mesh_sphere')
	src_pop.par.type = 'geodesic'; src_pop.par.freq = 16       # 20*16^2 = 5120 triangles
	for p in src_pop.pars('rad*'): p.val = 0.7   # radius par is a tuple in some builds
	src_pop.par.tx = 3.2; src_pop.par.ty = -0.3; src_pop.par.tz = 1.5
	src_pop.nodeX, src_pop.nodeY = -800, -600
	# real component inputs: In POP (mesh) + In TOPs (maps). When nothing is connected the defaults are used.
	in_mesh = get_or_create(rt, inPOP, 'in_mesh'); in_mesh.par.label = 'Mesh (P, N, vertex Tex)'
	in_mesh.nodeX, in_mesh.nodeY = -800, -700
	mesh_src = get_or_create(rt, switchPOP, 'mesh_src')
	mesh_src.inputConnectors[0].connect(src_pop); mesh_src.inputConnectors[1].connect(in_mesh)
	mesh_src.par.index.expr = "parent().fetch('in_mesh_on', 0)"
	mesh_src.nodeX, mesh_src.nodeY = -700, -600
	mesh_in = get_or_create(rt, nullPOP, 'mesh_in')
	mesh_in.inputConnectors[0].connect(mesh_src)
	mesh_in.nodeX, mesh_in.nodeY = -600, -600
	# default 'mat' (material id) and 'Color' attributes when the input mesh does not carry them
	defs = get_or_create(rt, attributePOP, 'mesh_attr_defaults')
	defs.inputConnectors[0].connect(mesh_in)
	defs.par.attr0name = 'custom'; defs.par.attr0customname = 'mat'; defs.par.attr0type = 'float'; defs.par.attr0numcomps = 1
	defs.par.attr1name = 'color'
	defs.par.overrideifexists = False; defs.par.notificationifexists = False
	defs.nodeX, defs.nodeY = -500, -600
	tri = get_or_create(rt, triangulatePOP, 'mesh_tri')
	tri.inputConnectors[0].connect(defs)
	tri.par.triangulatequads = True
	tri.nodeX, tri.nodeY = -400, -600
	conv = get_or_create(rt, attributeconvertPOP, 'mesh_verts')
	conv.inputConnectors[0].connect(tri)
	conv.par.convertop = 'pointtovert'
	conv.par.inputattrs = 'P N mat Color'
	conv.par.newattrs = 'VP VN VM VC'
	# texture coords: the sphere POP creates 'Tex' as a VERTEX attribute; any input mesh must provide vertex 'Tex'
	# (use a Texture Map POP or an Attribute Convert POP point->vertex before mesh_in if needed)
	conv.nodeX, conv.nodeY = -200, -600
	glsl.par.colpop = tri                 # acceleration structure = triangulated mesh
	glsl.par.input0pops = conv            # input 1: de-indexed vertex attributes (VP, VN, Tex)

	# In TOPs for the material maps (albedo, rough/metal, normal, emit); switches fall back to the built-in test maps
	in_tops = {}
	for i, (nm, lab) in enumerate((('albedo', 'Albedo map'), ('rm', 'Rough/Metal map (r, g)'), ('normal', 'Normal map'), ('emit', 'Emit map'))):
		it = get_or_create(rt, inTOP, 'in_' + nm); it.par.label = lab
		it.nodeX, it.nodeY = -1000, 500 - 100 * i
		in_tops[nm] = it

	# --- material maps (albedo, rough/metal, normal, emit). Replace freely.
	chk_src = get_or_create(rt, textDAT, 'checker_frag')
	chk_src.par.file = SHADERS + '/checker.frag'; chk_src.par.syncfile = True; chk_src.par.loadonstartpulse.pulse()
	chk_src.nodeX, chk_src.nodeY = -800, 500
	tex_albedo = get_or_create(rt, glslTOP, 'tex_albedo')
	tex_albedo.par.pixeldat = chk_src
	tex_albedo.par.outputresolution = 'custom'; tex_albedo.par.resolutionw = 512; tex_albedo.par.resolutionh = 512
	tex_albedo.par.vec0name = 'uChecker'; tex_albedo.par.vec0valuex = 8
	tex_albedo.nodeX, tex_albedo.nodeY = -600, 500
	tex_rm = get_or_create(rt, constantTOP, 'tex_rm')
	tex_rm.par.colorr = 0.4; tex_rm.par.colorg = 0.0; tex_rm.par.colorb = 0.0; tex_rm.par.alpha = 1
	tex_rm.par.outputresolution = 'custom'; tex_rm.par.resolutionw = 64; tex_rm.par.resolutionh = 64
	tex_rm.nodeX, tex_rm.nodeY = -600, 400
	nz = get_or_create(rt, noiseTOP, 'tex_height')
	nz.par.outputresolution = 'custom'; nz.par.resolutionw = 512; nz.par.resolutionh = 512
	nz.par.mono = True
	nz.nodeX, nz.nodeY = -800, 300
	tex_normal = get_or_create(rt, normalmapTOP, 'tex_normal')
	tex_normal.inputConnectors[0].connect(nz)
	tex_normal.nodeX, tex_normal.nodeY = -600, 300
	tex_emit = get_or_create(rt, constantTOP, 'tex_emit')
	tex_emit.par.colorr = 0; tex_emit.par.colorg = 0; tex_emit.par.colorb = 0; tex_emit.par.alpha = 1
	tex_emit.par.outputresolution = 'custom'; tex_emit.par.resolutionw = 64; tex_emit.par.resolutionh = 64
	tex_emit.nodeX, tex_emit.nodeY = -600, 200
	# GLSL TOPs have 3 fixed inputs (0 = feedback) -> pack the 4 maps into a 2x2 atlas
	for nm, fname in (('atlas_a_frag', 'atlas_a.frag'), ('atlas_b_frag', 'atlas_b.frag')):
		d = get_or_create(rt, textDAT, nm); d.par.file = SHADERS + '/' + fname; d.par.syncfile = True; d.par.loadonstartpulse.pulse()
		d.nodeX, d.nodeY = -800, 100 if nm == 'atlas_a_frag' else 0
	atlas_a = get_or_create(rt, glslTOP, 'maps_atlas_a')
	atlas_a.par.pixeldat = rt.op('atlas_a_frag')
	atlas_a.par.outputresolution = 'custom'; atlas_a.par.resolutionw = 2048; atlas_a.par.resolutionh = 2048
	def tex_switch(nm, default_top):
		sw = get_or_create(rt, switchTOP, 'tex_' + nm + '_sw')
		sw.inputConnectors[0].connect(default_top); sw.inputConnectors[1].connect(in_tops[nm])
		sw.par.index.expr = "parent().fetch('in_%s_on', 0)" % nm
		sw.nodeX, sw.nodeY = default_top.nodeX + 120, default_top.nodeY
		return sw
	sw_albedo = tex_switch('albedo', tex_albedo); sw_rm = tex_switch('rm', tex_rm); sw_normal = tex_switch('normal', tex_normal); sw_emit = tex_switch('emit', tex_emit)
	atlas_a.inputConnectors[0].connect(sw_albedo); atlas_a.inputConnectors[1].connect(sw_rm); atlas_a.inputConnectors[2].connect(sw_normal)
	atlas_a.nodeX, atlas_a.nodeY = -400, 500
	atlas_b = get_or_create(rt, glslTOP, 'maps_atlas')
	atlas_b.par.pixeldat = rt.op('atlas_b_frag')
	atlas_b.par.outputresolution = 'custom'; atlas_b.par.resolutionw = 2048; atlas_b.par.resolutionh = 2048
	atlas_b.inputConnectors[0].connect(atlas_a); atlas_b.inputConnectors[1].connect(sw_emit)
	atlas_b.nodeX, atlas_b.nodeY = -200, 500
	glsl.par.sampler1name = 'sAtlas'; glsl.par.sampler1top = atlas_b

	# environment map (equirectangular): in_env or a generated dark studio with blue/orange streaks
	in_env = get_or_create(rt, inTOP, 'in_env'); in_env.par.label = 'Environment map (equirect)'
	in_env.nodeX, in_env.nodeY = -1000, 700
	env_src = get_or_create(rt, textDAT, 'env_frag')
	env_src.par.file = SHADERS + '/env_default.frag'; env_src.par.syncfile = True; env_src.par.loadonstartpulse.pulse()
	env_src.nodeX, env_src.nodeY = -800, 700
	env_default = get_or_create(rt, glslTOP, 'env_default')
	env_default.par.pixeldat = env_src
	env_default.par.outputresolution = 'custom'; env_default.par.resolutionw = 1024; env_default.par.resolutionh = 512; env_default.par.format = 'rgba16float'
	env_default.par.vec0name = 'uTime'; env_default.par.vec0valuex.expr = 'absTime.seconds'
	env_default.nodeX, env_default.nodeY = -600, 700
	env_sw = get_or_create(rt, switchTOP, 'env_sw')
	env_sw.inputConnectors[0].connect(env_default); env_sw.inputConnectors[1].connect(in_env)
	env_sw.par.index.expr = "parent().fetch('in_env_on', 0)"
	env_sw.nodeX, env_sw.nodeY = -400, 700
	glsl.par.sampler2name = 'sEnv'; glsl.par.sampler2top = env_sw
	glsl.par.vec10name = 'uMeshBound'
	glsl.par.vec10valuex.expr = 'parent().par.Meshboundcx'; glsl.par.vec10valuey.expr = 'parent().par.Meshboundcy'; glsl.par.vec10valuez.expr = 'parent().par.Meshboundcz'; glsl.par.vec10valuew.expr = 'parent().par.Meshboundr'
	glsl.par.vec11name = 'uMeshMat'
	glsl.par.vec11valuex.expr = 'parent().par.Meshmetallic'; glsl.par.vec11valuey.expr = 'parent().par.Meshrough'
	glsl.par.vec12name = 'uMeshColor'
	glsl.par.vec12valuex.expr = 'parent().par.Meshcolorr'; glsl.par.vec12valuey.expr = 'parent().par.Meshcolorg'; glsl.par.vec12valuez.expr = 'parent().par.Meshcolorb'

	out = get_or_create(rt, nullTOP, 'out_final')
	out.inputConnectors[0].connect(sw)
	out.nodeX, out.nodeY = 900, 0
	mo = get_or_create(rt, moviefileoutTOP, 'movieout')
	mo.inputConnectors[0].connect(out)
	mo.par.type = 'imagesequence' if 'imagesequence' in mo.par.type.menuNames else mo.par.type.menuNames[0]
	if 'png' in mo.par.imagefiletype.menuNames: mo.par.imagefiletype = 'png'
	mo.par.file.expr = 'parent().par.Offlinefile + me.fileSuffix'     # image sequence: TD appends .NNNN.png via me.fileSuffix
	mo.par.record.expr = 'parent().par.Record'
	mo.nodeX, mo.nodeY = 1100, -100
	rt.store('movieout_type_menu', mo.par.type.menuNames)
	out.viewer = True
	return rt

rt = build()
