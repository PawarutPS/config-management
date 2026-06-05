@Library('pipeline-utils@main') _

def environments = [
  develop: [
    aws_region: 'ap-southeast-1',
    aws_creds_id: 'aws-sit-creds',
    backup_s3_bucket: 'replace-with-sit-config-backup-bucket',
    backup_s3_prefix: 'dynamodb-config-backup'
  ],
  release: [
    aws_region: 'ap-southeast-7',
    aws_creds_id: 'aws-uat-creds',
    backup_s3_bucket: 'replace-with-uat-config-backup-bucket',
    backup_s3_prefix: 'dynamodb-config-backup'
  ],
  main: [
    aws_region: 'ap-southeast-7',
    aws_creds_id: 'aws-prd-creds',
    backup_s3_bucket: 'replace-with-prd-config-backup-bucket',
    backup_s3_prefix: 'dynamodb-config-backup'
  ]
]

pipeline {
  agent any

  environment {
    IMAGE_TAG = "${env.GIT_COMMIT.substring(0, 7)}"
    REPOSITORY = "xxx/xxx"
    PROJECT_DIR = "xxx"
    TEAMS_WEBHOOK_URL = credentials('workflow-webhook-url')
    DEPLOY_ENV = "${env.BRANCH_NAME == 'main' ? 'production' : (env.BRANCH_NAME == 'release' ? 'uat' : 'dev')}"
    CHANGED_BASE = "${env.GIT_PREVIOUS_SUCCESSFUL_COMMIT ?: 'HEAD~1'}"
    CHANGED_HEAD = 'HEAD'
  }

  stages {
    stage('Resolve Environment') {
      steps {
        script {
          config = environments[env.BRANCH_NAME]
          if (config == null) {
            error "Unsupported branch for deploy: ${env.BRANCH_NAME}"
          }
        }
      }
    }

    stage('Install') {
      steps {
        sh 'python3 -m pip install -r requirements.txt'
        sh 'python3 -m pip install -e .'
      }
    }

    stage('Generate CLI') {
      steps {
        script {
          env.DEPLOY_CMD = """
            python3 dynamodb_config_manager/cli.py \
              --scope changed \
              --changed-base ${CHANGED_BASE} \
              --changed-head ${CHANGED_HEAD} \
              --no-dry-run \
              --clear-table \
              --confirm-clear \
              --delete-removed-tables \
              --confirm-delete-tables \
              --backup-s3-bucket ${config.backup_s3_bucket} \
              --backup-s3-prefix ${config.backup_s3_prefix}
          """.trim()
          print env.DEPLOY_CMD
        }
      }
    }

    stage('Deploy Changed CSV') {
      steps {
        script {
          withAWS(region: config.aws_region, credentials: config.aws_creds_id) {
            sh '$DEPLOY_CMD'
          }
        }
      }
    }
  }
}
