pipeline {
  agent any
  options { 
    disableConcurrentBuilds() 
  }

  environment {
      INMANTA_TEST_ENV="${env.WORKSPACE}/env"
  } 

  stages {
    stage("stage"){
      steps{
        script{
          checkout changelog: false, poll: false, scm: [$class: 'GitSCM', branches: [[name: '*/master']], doGenerateSubmoduleConfigurations: false, extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'inmanta']], submoduleCfg: [], userRemoteConfigs: [[credentialsId: 'inmantaci', url: 'https://github.com/inmanta/inmanta.git']]]
          checkout changelog: false, poll: false, scm: [$class: 'GitSCM', branches: [[name: '*/master']], doGenerateSubmoduleConfigurations: false, extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'std']], submoduleCfg: [], userRemoteConfigs: [[credentialsId: 'inmantaci', url: 'https://github.com/inmanta/std.git']]]
          sh 'rm -rf $INMANTA_TEST_ENV; python3 -m venv $INMANTA_TEST_ENV; $INMANTA_TEST_ENV/bin/python3 -m pip install --upgrade pip'
          sh 'grep -v inmanta-sphinx inmanta/requirements.txt >requirements.txt' // can not have constraint on self
          sh '$INMANTA_TEST_ENV/bin/python3 -m pip install -U -c inmanta/requirements.txt inmanta sphinx-argparse sphinx-autodoc-annotation sphinx-rtd-theme'
          sh '$INMANTA_TEST_ENV/bin/python3 -m pip install -U -c requirements.txt .'
          sh 'rm -rf inmanta/docs/reference/modules; mkdir inmanta/docs/reference/modules'
        }
      }
    }
    stage("test"){
      steps{
        script{
          sh '$INMANTA_TEST_ENV/bin/python3 -m sphinxcontrib.inmanta.api --module_repo $(pwd) --module std --source-repo https://github.com/inmanta/ --file inmanta/docs/reference/modules/std.rst'
          sh '$INMANTA_TEST_ENV/bin/python3 -m sphinx.cmd.build -b html inmanta/docs build'
        }
      }
    }
  }
}
