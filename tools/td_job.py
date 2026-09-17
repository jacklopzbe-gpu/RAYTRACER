# JOB: build the portable reference project from a toe located in the repo root (relative paths).
exec(open(ROOT + '/td/build_network.py', encoding='utf-8').read(), {'__name__': 'build'})
exec(open(ROOT + '/td/demo_ribbons.py', encoding='utf-8').read(), {'__name__': 'demo'})
rt = op('/project1/rt')
log('ROOT', ROOT, '| project.folder', project.folder, '| common_glsl file par:', rt.op('common_glsl').par.file.eval(), '| accum file:', rt.op('accum_ctl').par.file.eval(), '| offline file:', rt.par.Offlinefile.eval())
log('text loaded?', len(rt.op('common_glsl').text) > 100, len(rt.op('trace_glsl').text) > 100, '| errors', repr(rt.op('trace_pop').errors()), repr(rt.op('trace_pop').warnings()), '| ctl errors', repr(rt.op('accum_ctl').errors()))
rt.par.top = rt.op('out_final'); rt.op('out_final').viewer = True
op('/project1/boot').destroy()
def f1():
	import os, glob
	a = rt.op('acc').numpyArray(); log('render ok: count', float(a[...,3].max()), 'mean', round(float(a[...,:3].mean()),4))
	rt.op('out_final').save(ROOT + '/tests/renders/reference_build.png')
	for b in glob.glob(ROOT + '/RAYTRACER_reference*.toe'): os.remove(b)
	project.save(ROOT + '/RAYTRACER_reference.toe')
	for b in glob.glob(ROOT + '/RAYTRACER_reference.*.toe'): os.remove(b)
	log('saved'); log('JOB done'); run("project.quit(force=True)", delayFrames=5)
run('args[0]()', f1, delayFrames=90)
