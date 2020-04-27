pipeline {
  agent any
  options {
    disableConcurrentBuilds()
  }

  parameters
  {
    string(name: 'CORE_BRANCH', defaultValue: 'master', description: 'branch in the inmanta repo')
  }

  environment {
      INMANTA_TEST_ENV="${env.WORKSPACE}/env"
  }

  stages {
    stage("stage"){
      steps{
        script{
          checkout changelog: false, poll: false, scm: [$class: 'GitSCM', branches: [[name: params.CORE_BRANCH]], doGenerateSubmoduleConfigurations: false, extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'inmanta']], submoduleCfg: [], userRemoteConfigs: [[credentialsId: 'inmantaci', url: 'https://github.com/inmanta/inmanta.git']]]
          checkout changelog: false, poll: false, scm: [$class: 'GitSCM', branches: [[name: '*/master']], doGenerateSubmoduleConfigurations: false, extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'std']], submoduleCfg: [], userRemoteConfigs: [[credentialsId: 'inmantaci', url: 'https://github.com/inmanta/std.git']]]
          sh 'rm -rf $INMANTA_TEST_ENV; python3 -m venv $INMANTA_TEST_ENV; $INMANTA_TEST_ENV/bin/python3 -m pip install --upgrade pip'
          sh 'grep -v inmanta-sphinx inmanta/requirements.txt >requirements.txt' // can not have constraint on self
          // install latest inmanta and not from release
          sh '$INMANTA_TEST_ENV/bin/python3 -m pip install -U -c inmanta/requirements.txt ./inmanta'
          // install sphinx and plugins
          sh '$INMANTA_TEST_ENV/bin/python3 -m pip install -U -c inmanta/requirements.txt sphinx-argparse sphinx-autodoc-annotation sphinx-rtd-theme sphinxcontrib-serializinghtml sphinx-tabs'
          // install inmanta sphinx
          sh '$INMANTA_TEST_ENV/bin/python3 -m pip install -U -c requirements.txt .'
          sh 'rm -rf inmanta/docs/reference/modules; mkdir inmanta/docs/reference/modules'
        }
      }
    }
    stage("test"){
      steps{
        script{
          sh '$INMANTA_TEST_ENV/bin/python3 -m sphinxcontrib.inmanta.api --module_repo $(pwd) --module std --source-repo https://github.com/inmanta/ --file inmanta/docs/reference/modules/std.rst'
          sh '$INMANTA_TEST_ENV/bin/python3 -m sphinx.cmd.build -vv -T -b html inmanta/docs build'
        }
      }
    }
  }
}
