window.REVIEW_DATA = {
  "public_mode": true,
  "generated_at": "(local build)",
  "lenses": [
    "security"
  ],
  "summary": {
    "awaiting": 1,
    "decided": 1,
    "rubric_changes_30d": 1,
    "total_cases": 2,
    "total_projects": 2
  },
  "lens_health": {
    "資安": {
      "produced": 1,
      "total": 1,
      "has_rubric": true
    },
    "風管": {
      "produced": 0,
      "total": 1,
      "has_rubric": false
    },
    "法遵": {
      "produced": 0,
      "total": 1,
      "has_rubric": false
    }
  },
  "schedule": [
    {
      "name": "daily-digest",
      "type": "digest",
      "status": "implemented"
    },
    {
      "name": "feedback-synthesis",
      "type": "feedback-synthesis",
      "status": "implemented"
    },
    {
      "name": "overdue-reminder",
      "type": "reminder",
      "status": "skeleton"
    },
    {
      "name": "submission-patrol",
      "type": "patrol",
      "status": "skeleton"
    }
  ],
  "projects": [
    {
      "project_id": "payments-service",
      "project_name": "Payments Service",
      "review_count": 1,
      "open_count": 1,
      "latest_verdict": "no-go",
      "total_blockers": 3
    },
    {
      "project_id": "notification-hub",
      "project_name": "Notification Hub",
      "review_count": 1,
      "open_count": 0,
      "latest_verdict": "go",
      "total_blockers": 0
    }
  ],
  "departments": [
    {
      "lens": "security",
      "name": "資安",
      "full": "資訊安全",
      "has_rubric": true
    },
    {
      "lens": "risk",
      "name": "風管",
      "full": "風險管理",
      "has_rubric": false
    },
    {
      "lens": "legal",
      "name": "法遵",
      "full": "法令遵循",
      "has_rubric": false
    }
  ],
  "cab_gates": [
    {
      "id": "CAB1",
      "name": "CAB1",
      "env": "UT",
      "desc": "部署到 UT(測試)環境前的審查關卡"
    },
    {
      "id": "CAB2",
      "name": "CAB2",
      "env": "PROD",
      "desc": "部署到 PROD(正式)環境前的審查關卡"
    }
  ],
  "cab_workflow": [
    "提案",
    "文件 Review",
    "審核會議",
    "會議記錄"
  ],
  "cases": [
    {
      "case_id": "2026-0627-062747-C0DEMO123",
      "project_id": "payments-service",
      "project_name": "Payments Service",
      "status": "awaiting-signoff",
      "verdict": "no-go",
      "severity": {
        "blocker": 3,
        "high": 3,
        "medium": 5,
        "low": 1,
        "info": 0
      },
      "blockers": 3,
      "finding_count": 12,
      "demo": false,
      "cabs": [
        {
          "id": "CAB1",
          "name": "CAB1",
          "env": "UT",
          "desc": "部署到 UT(測試)環境前的審查關卡",
          "workflow": [
            "提案",
            "文件 Review",
            "審核會議",
            "會議記錄"
          ],
          "reviewed": true,
          "blockers": 3,
          "verdict": "no-go",
          "finding_count": 9,
          "doc_view": [
            {
              "doc": "文件 1",
              "finding_count": 9,
              "blockers": 3
            }
          ],
          "dept_view": [
            {
              "lens": "security",
              "name": "資安",
              "full": "資訊安全",
              "has_rubric": true,
              "advice": "no-go",
              "covered": true,
              "finding_count": 7
            },
            {
              "lens": "risk",
              "name": "風管",
              "full": "風險管理",
              "has_rubric": false,
              "advice": "conditional-go",
              "covered": true,
              "finding_count": 1
            },
            {
              "lens": "legal",
              "name": "法遵",
              "full": "法令遵循",
              "has_rubric": false,
              "advice": "go",
              "covered": true,
              "finding_count": 1
            }
          ]
        },
        {
          "id": "CAB2",
          "name": "CAB2",
          "env": "PROD",
          "desc": "部署到 PROD(正式)環境前的審查關卡",
          "workflow": [
            "提案",
            "文件 Review",
            "審核會議",
            "會議記錄"
          ],
          "reviewed": true,
          "blockers": 0,
          "verdict": "conditional-go",
          "finding_count": 3,
          "doc_view": [
            {
              "doc": "文件 1",
              "finding_count": 1,
              "blockers": 0
            },
            {
              "doc": "文件 2",
              "finding_count": 2,
              "blockers": 0
            }
          ],
          "dept_view": [
            {
              "lens": "security",
              "name": "資安",
              "full": "資訊安全",
              "has_rubric": true,
              "advice": "conditional-go",
              "covered": true,
              "finding_count": 1
            },
            {
              "lens": "risk",
              "name": "風管",
              "full": "風險管理",
              "has_rubric": false,
              "advice": "go",
              "covered": true,
              "finding_count": 1
            },
            {
              "lens": "legal",
              "name": "法遵",
              "full": "法令遵循",
              "has_rubric": false,
              "advice": "go",
              "covered": true,
              "finding_count": 1
            }
          ]
        }
      ]
    },
    {
      "case_id": "2026-0620-090000-NOTIFY",
      "project_id": "notification-hub",
      "project_name": "Notification Hub",
      "status": "decided",
      "verdict": "go",
      "severity": {
        "blocker": 0,
        "high": 0,
        "medium": 1,
        "low": 2,
        "info": 0
      },
      "blockers": 0,
      "finding_count": 3,
      "demo": true,
      "cabs": [
        {
          "id": "CAB1",
          "name": "CAB1",
          "env": "UT",
          "desc": "部署到 UT(測試)環境前的審查關卡",
          "workflow": [
            "提案",
            "文件 Review",
            "審核會議",
            "會議記錄"
          ],
          "reviewed": true,
          "blockers": 0,
          "verdict": "go",
          "finding_count": 2,
          "doc_view": [
            {
              "doc": "文件 1",
              "finding_count": 1,
              "blockers": 0
            },
            {
              "doc": "文件 2",
              "finding_count": 1,
              "blockers": 0
            }
          ],
          "dept_view": [
            {
              "lens": "security",
              "name": "資安",
              "full": "資訊安全",
              "has_rubric": true,
              "advice": "go",
              "covered": true,
              "finding_count": 1
            },
            {
              "lens": "risk",
              "name": "風管",
              "full": "風險管理",
              "has_rubric": false,
              "advice": "go",
              "covered": true,
              "finding_count": 1
            },
            {
              "lens": "legal",
              "name": "法遵",
              "full": "法令遵循",
              "has_rubric": false,
              "advice": "pending",
              "covered": false,
              "finding_count": 0
            }
          ]
        },
        {
          "id": "CAB2",
          "name": "CAB2",
          "env": "PROD",
          "desc": "部署到 PROD(正式)環境前的審查關卡",
          "workflow": [
            "提案",
            "文件 Review",
            "審核會議",
            "會議記錄"
          ],
          "reviewed": true,
          "blockers": 0,
          "verdict": "go",
          "finding_count": 1,
          "doc_view": [
            {
              "doc": "文件 1",
              "finding_count": 1,
              "blockers": 0
            }
          ],
          "dept_view": [
            {
              "lens": "security",
              "name": "資安",
              "full": "資訊安全",
              "has_rubric": true,
              "advice": "go",
              "covered": true,
              "finding_count": 1
            },
            {
              "lens": "risk",
              "name": "風管",
              "full": "風險管理",
              "has_rubric": false,
              "advice": "pending",
              "covered": false,
              "finding_count": 0
            },
            {
              "lens": "legal",
              "name": "法遵",
              "full": "法令遵循",
              "has_rubric": false,
              "advice": "pending",
              "covered": false,
              "finding_count": 0
            }
          ]
        }
      ]
    }
  ],
  "skills": {
    "rubrics": [
      {
        "name": "review-legal",
        "path": "rubrics/review-legal.md",
        "last_sha": "0674148",
        "last_date": "2026-06-27",
        "last_subject": "Initial scaffold + runnable Step 1 (Slack Socket Mode listener)"
      },
      {
        "name": "review-ops",
        "path": "rubrics/review-ops.md",
        "last_sha": "0674148",
        "last_date": "2026-06-27",
        "last_subject": "Initial scaffold + runnable Step 1 (Slack Socket Mode listener)"
      },
      {
        "name": "review-privacy",
        "path": "rubrics/review-privacy.md",
        "last_sha": "0674148",
        "last_date": "2026-06-27",
        "last_subject": "Initial scaffold + runnable Step 1 (Slack Socket Mode listener)"
      },
      {
        "name": "review-security",
        "path": "rubrics/review-security.md",
        "last_sha": "0674148",
        "last_date": "2026-06-27",
        "last_subject": "Initial scaffold + runnable Step 1 (Slack Socket Mode listener)"
      }
    ],
    "skills": [
      {
        "name": "intake-completeness",
        "path": "skills/intake-completeness/SKILL.md",
        "last_sha": "0674148",
        "last_date": "2026-06-27",
        "last_subject": "Initial scaffold + runnable Step 1 (Slack Socket Mode listener)"
      },
      {
        "name": "review-security",
        "path": "skills/review-security/SKILL.md",
        "last_sha": "0674148",
        "last_date": "2026-06-27",
        "last_subject": "Initial scaffold + runnable Step 1 (Slack Socket Mode listener)"
      },
      {
        "name": "run-review",
        "path": "skills/run-review/SKILL.md",
        "last_sha": "0674148",
        "last_date": "2026-06-27",
        "last_subject": "Initial scaffold + runnable Step 1 (Slack Socket Mode listener)"
      }
    ],
    "agents": [
      {
        "name": "intake",
        "path": "agents/intake.md",
        "last_sha": "0674148",
        "last_date": "2026-06-27",
        "last_subject": "Initial scaffold + runnable Step 1 (Slack Socket Mode listener)"
      },
      {
        "name": "review-lens",
        "path": "agents/review-lens.md",
        "last_sha": "0674148",
        "last_date": "2026-06-27",
        "last_subject": "Initial scaffold + runnable Step 1 (Slack Socket Mode listener)"
      },
      {
        "name": "synthesizer",
        "path": "agents/synthesizer.md",
        "last_sha": "0674148",
        "last_date": "2026-06-27",
        "last_subject": "Initial scaffold + runnable Step 1 (Slack Socket Mode listener)"
      }
    ]
  },
  "proposals": [
    {
      "target": "sec-authz",
      "feedback_count": 1
    },
    {
      "target": "sec-deps",
      "feedback_count": 1
    },
    {
      "target": "sec-pentest",
      "feedback_count": 1
    }
  ],
  "feedback_summary": {
    "total": 3
  },
  "rubric_changes_30d": 1
};
