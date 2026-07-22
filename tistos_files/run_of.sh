echo 'test_in_sh'
foamCaseDir=$1
procPerJob=$2
cd $foamCaseDir
mpiexec --oversubscribe -n $procPerJob -v simpleFoam -parallel > log.mpiexec 2>&1
echo 'finished'
