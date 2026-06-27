window.REVIEW_DATA = {
  "public_mode": true,
  "generated_at": "demo build",
  "lenses": [
    "security"
  ],
  "summary": {
    "awaiting": 1,
    "decided": 2,
    "rubric_changes_30d": 1,
    "total_cases": 3,
    "total_projects": 2
  },
  "lens_health": {
    "security": {
      "produced": 1,
      "total": 1
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
      "review_count": 2,
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
  "cases": [
    {
      "case_id": "2026-0627-062747-C0DEMO123",
      "project_id": "payments-service",
      "project_name": "Payments Service",
      "status": "awaiting-signoff",
      "verdict": "no-go",
      "severity": {
        "blocker": 3,
        "high": 1,
        "medium": 3,
        "low": 0,
        "info": 0
      },
      "blockers": 3,
      "finding_count": 7,
      "demo": false
    },
    {
      "case_id": "2026-0312-101500-PAYMENTS-V1",
      "project_id": "payments-service",
      "project_name": "Payments Service",
      "status": "decided",
      "verdict": "conditional-go",
      "severity": {
        "blocker": 0,
        "high": 1,
        "medium": 1,
        "low": 0,
        "info": 0
      },
      "blockers": 0,
      "finding_count": 2,
      "demo": true
    },
    {
      "case_id": "2026-0620-090000-NOTIFY-V2",
      "project_id": "notification-hub",
      "project_name": "Notification Hub",
      "status": "decided",
      "verdict": "go",
      "severity": {
        "blocker": 0,
        "high": 0,
        "medium": 0,
        "low": 1,
        "info": 0
      },
      "blockers": 0,
      "finding_count": 1,
      "demo": true
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
  "rubric_changes_30d": 1,
  "workflow_stages": [
    "Intake",
    "Review",
    "Synthesize",
    "Sign-off"
  ]
};
