# Runs inside TouchDesigner (Execute DAT onStart of tools/RayTest.toe).
# Executes tools/td_job.py, logs everything to tools/td_log.txt.
# The job must call project.quit(force=True) itself when done; a watchdog quits anyway after ~2 min.
import os, traceback, time
ROOT = (project.folder if os.path.exists(os.path.join(project.folder, 'shaders')) else os.path.dirname(project.folder)).replace(chr(92), '/')   # toe in repo root or in tools/
LOG = os.path.join(ROOT, 'tools', 'td_log.txt')
def log(*a):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(' '.join(str(x) for x in a) + '\n')
try:
    open(LOG, 'w').close()
    import glob
    for b in glob.glob(os.path.join(ROOT, 'tests', 'RAYTRACER_test.*.toe')): os.remove(b)
    log('BOOT', time.strftime('%Y-%m-%d %H:%M:%S'), 'build', app.build, 'version', app.version, 'product', app.product)
    log('license', app.licenseType if hasattr(app, 'licenseType') else '?')
    run("project.quit(force=True)", delayFrames=60*150)   # watchdog
    g = {'__name__': 'td_job', 'log': log, 'ROOT': ROOT}
    exec(open(os.path.join(ROOT, 'tools', 'td_job.py'), encoding='utf-8').read(), g)
except Exception:
    log('BOOT EXCEPTION\n' + traceback.format_exc())
    run("project.quit(force=True)", delayFrames=30)
