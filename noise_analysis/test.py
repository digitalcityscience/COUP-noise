import os
import shlex, subprocess

# Feeds the geodatabase with the design data and performs the noise computation
# Returns the path of the resulting geojson
def get_cwd():
    return os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    orbisgis_dir = get_cwd() + '/orbisgis_java/'

    java_command = 'java -cp "bin/*:bundle/*:sys-bundle/*" org.h2.tools.Server -pg -trace -tcp -tcpAllowOthers'

    args = shlex.split(java_command)
    f = open("log.txt", "w+")
    p = subprocess.Popen(args, cwd=orbisgis_dir, stdout=f)

    print("db started")

    while p.poll() is None:
        stdout, stderr = p.communicate()
        print(stdout, stderr)

    # process exited
    print(p.poll(), "Exited")
    print(stdout, stderr)