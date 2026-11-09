// Deezer → Navidrome pipeline: every commit builds the Android app and the
// image that ships it, and checks the container answers on /health; only
// `main` pushes the image.
pipeline {
  agent { label 'docker' }

  options {
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
    // The first Android build downloads the SDK and Gradle's dependencies.
    timeout(time: 45, unit: 'MINUTES')
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

    stage('Android') {
      // Builds and signs the app in Docker (android/Dockerfile) into dist/android,
      // which the image built next ships. The key lives in two credentials:
      // android-keystore (secret file) and android-keystore-password (secret text).
      steps {
        sh 'rm -rf dist/android'
        script {
          def keyFound = true
          try {
            // Only a missing credential can fail this empty block.
            withCredentials([file(credentialsId: 'android-keystore', variable: 'KS_PROBE'),
                             string(credentialsId: 'android-keystore-password', variable: 'KS_PASS_PROBE')]) { }
          } catch (err) {
            keyFound = false
          }
          if (!keyFound) {
            if (env.IS_MAIN == 'true') {
              error('No Android signing key in Jenkins (android-keystore, android-keystore-password): an image from main must carry the app.')
            }
            echo 'WARNING: no Android signing key in Jenkins: this image is built without the app.'
            env.HAS_APK = 'false'
          } else {
            withCredentials([file(credentialsId: 'android-keystore', variable: 'D2N_KEYSTORE_FILE'),
                             string(credentialsId: 'android-keystore-password', variable: 'D2N_KEYSTORE_PASSWORD')]) {
              sh 'bash android/scripts/build-apk.sh'
            }
            env.HAS_APK = 'true'
          }
        }
        archiveArtifacts artifacts: 'dist/android/*', allowEmptyArchive: true, fingerprint: true
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
        // The app the Android stage built must be in the image.
        sh '''
          if [ "$HAS_APK" = "true" ]; then
            docker exec $CONTAINER python -c "from core import android_app; import sys; sys.exit(0 if android_app.info()['available'] else 1)" \
              || { echo "The image does not carry the Android app the Android stage built"; exit 1; }
            echo "The image carries the Android app"
          fi
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
