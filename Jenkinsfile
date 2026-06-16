@Library('pipeline-utils@main') _

def deployOutput = ''
def deployExitCode = 0


def parseDeployOutputV2(String output, int exitCode = 0) {
  def result = [
    status: exitCode == 0 ? 'SUCCESS' : 'FAILURE',
    filesProcessed: [],
    filesCount: 0,
    fileRowCounts: '',
    table: [],
    rowsRead: 0,
    rowsUpserted: 0,
    rowsFailed: 0,
    tablesDeleted: 0,
    s3Backup: '',
    errors: []
  ]

  def section = null
  output.readLines().each { rawLine ->
    def line = rawLine.trim()
    if (!line) {
      return
    }

    if (line in ['Files Processed', 'Files Count', 'File Row Counts', 'Table', 'Rows Read', 'Rows Upserted', 'Rows Failed', 'Tables Deleted', 'S3 Backup', 'Status', 'Errors']) {
      section = line
      return
    }

    if (!line.startsWith('-')) {
      return
    }

    def value = line.replaceFirst(/^-\s*/, '')
    switch (section) {
      case 'Files Processed':
        result.filesProcessed << value
        break
      case 'Files Count':
        result.filesCount = value.isInteger() ? value.toInteger() : 0
        break
      case 'File Row Counts':
        result.fileRowCounts = result.fileRowCounts ? "${result.fileRowCounts}\n${value}" : value
        break
      case 'Table':
        result.table << value
        break
      case 'Rows Read':
        result.rowsRead = value.isInteger() ? value.toInteger() : 0
        break
      case 'Rows Upserted':
        result.rowsUpserted = value.isInteger() ? value.toInteger() : 0
        break
      case 'Rows Failed':
        result.rowsFailed = value.isInteger() ? value.toInteger() : 0
        break
      case 'Tables Deleted':
        result.tablesDeleted = value.isInteger() ? value.toInteger() : 0
        break
      case 'S3 Backup':
        result.s3Backup = result.s3Backup ? "${result.s3Backup}\n${value}" : value
        break
      case 'Status':
        result.status = exitCode == 0 ? value : 'FAILURE'
        break
      case 'Errors':
        result.errors << value
        break
    }
  }

  if (result.errors) {
    result.message = result.errors.join('\n')
  }

  return result
}

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
          env.DEPLOY_CMD = [
            'python3 dynamodb_config_manager/cli.py',
            '--scope changed',
            "--changed-base ${CHANGED_BASE}",
            "--changed-head ${CHANGED_HEAD}",
            '--no-dry-run',
            '--clear-table',
            '--confirm-clear',
            '--delete-removed-tables',
            '--confirm-delete-tables',
            "--backup-s3-bucket ${config.backup_s3_bucket}",
            "--backup-s3-prefix ${config.backup_s3_prefix}"
          ].join(' ')
          print env.DEPLOY_CMD
        }
      }
    }

    stage('Deploy Changed CSV') {
      steps {
        script {
          withAWS(region: config.aws_region, credentials: config.aws_creds_id) {
            def rawDeployOutput = sh(
              script: """
                set +e
                ${env.DEPLOY_CMD} 2>&1
                exit_code=\$?
                echo "__EXIT_CODE:\${exit_code}"
                exit 0
              """,
              returnStdout: true
            ).trim()

            def exitMatcher = rawDeployOutput =~ /__EXIT_CODE:(\d+)/
            deployExitCode = exitMatcher ? exitMatcher[0][1].toInteger() : 1
            deployOutput = rawDeployOutput.replaceAll(/(?m)^__EXIT_CODE:\d+\s*$/, '').trim()
            print deployOutput
          }
        }
      }
    }

    stage('Notification Changed CSV') {
      steps {
        script {
          def result = parseDeployOutputV2(deployOutput, deployExitCode)

          def payload = buildFlexibleTeamsPayloadV2([
            teamId: '4a05139b-373f-4f56-a40a-11b7745ea94e',
            channelId: '19:b447003c4a4e4274a0444f633817f2b6@thread.tacv2',
            status: result.status,
            header: 'Upload Config Completed',
            subtitle: "Job: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
            filesProcessed: result.filesProcessed,
            table: result.table,
            rowsRead: result.rowsRead,
            rowsUpserted: result.rowsUpserted,
            rowsFailed: result.rowsFailed,
            tablesDeleted: result.tablesDeleted,
            message: result.message,
            extraFacts: [
              [title: 'Files Count', value: result.filesCount],
              [title: 'File Row Counts', value: result.fileRowCounts ?: '-'],
              [title: 'S3 Backup', value: result.s3Backup ?: '-'],
              [title: 'Environment', value: env.DEPLOY_ENV ?: '-']
            ],
            buildUrl: env.BUILD_URL
          ])

          sendTeamsMessageV2(this, env.TEAMS_WEBHOOK_URL, payload)
        }
      }
    }

    stage('Finalize Deploy Result') {
      steps {
        script {
          if (deployExitCode != 0) {
            error "DynamoDB config deploy failed with exit code ${deployExitCode}"
          }
        }
      }
    }
  }
}
