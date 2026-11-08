// Deezer → Navidrome pipeline: every commit builds the image and checks the
// container answers on /health; only `main` pushes the image.
pipeline {
  agent { label 'docker' }

  options {
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
    timeout(time: 20, unit: 'MINUTES')
  }

  environment {
    IMAGE = 'catchow/deezer-to-navidrome'
  }

  stages {
    stage('Infos') {
      steps {
        script {
          env.SHA     = env.GIT_COMMIT.take(7)
          env.VERSION = readFile('VERSION').trim()
          // Multibranch jobs set BRANCH_NAME, plain pipeline jobs GIT_BRANCH (origin/main).
          env.IS_MAIN = ((env.BRANCH_NAME ?: env.GIT_BRANCH ?: '') ==~ /(origin\/)?main/).toString()
          currentBuild.displayName = "#${env.BUILD_NUMBER} v${env.VERSION} (${env.SHA})"
        }
        echo "Image : ${IMAGE} | version : ${VERSION} | commit : ${SHA} | publish : ${IS_MAIN}"
      }
    }

    stage('Image') {
      steps {
        // Only the commit tag here. A "latest" built locally can be swapped for the
        // one on Docker Hub by any pull on this Docker host (a compose pull, an
        // updater) before it is pushed: 1.15.0 shipped with the 1.14.0 image that way.
        sh 'docker build --pull -t $IMAGE:$SHA .'
      }
    }

    stage('Smoke test') {
      // Starts the image and waits for gunicorn to answer on /health.
      // Python's urllib is used because the image ships neither curl nor wget.
      environment {
        CONTAINER = "d2n-ci-${env.BUILD_NUMBER}"
      }
      steps {
        sh 'docker run -d --name $CONTAINER $IMAGE:$SHA'
        sh '''
          for i in $(seq 1 30); do
            if docker exec $CONTAINER python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)" 2>/dev/null; then
              echo "Container healthy after ${i}s"
              exit 0
            fi
            sleep 1
          done
          echo "Container did not answer on /health"
          docker logs $CONTAINER
          exit 1
        '''
      }
      post {
        always {
          sh 'docker rm -f $CONTAINER || true'
        }
      }
    }

    stage('Push') {
      when { environment name: 'IS_MAIN', value: 'true' }
      steps {
        withCredentials([usernamePassword(credentialsId: 'registry-creds',
                         usernameVariable: 'REG_USER', passwordVariable: 'REG_PASS')]) {
          sh 'echo "$REG_PASS" | docker login -u "$REG_USER" --password-stdin'
          sh 'docker push $IMAGE:$SHA'
          // The version and latest are copied on Docker Hub from the commit just
          // pushed, so no local tag can slip in between.
          sh 'docker buildx imagetools create -t $IMAGE:$VERSION -t $IMAGE:latest $IMAGE:$SHA'
          sh '''
            want=$(docker buildx imagetools inspect $IMAGE:$SHA --format '{{.Manifest.Digest}}')
            for tag in $VERSION latest; do
              got=$(docker buildx imagetools inspect $IMAGE:$tag --format '{{.Manifest.Digest}}')
              echo "$tag -> $got"
              if [ "$got" != "$want" ]; then
                echo "$IMAGE:$tag is $got, expected $want (the image of $SHA)"
                exit 1
              fi
            done
          '''
        }
      }
    }
  }

  post {
    always {
      sh 'docker logout || true'
      sh 'docker image prune -f || true'
    }
  }
}
