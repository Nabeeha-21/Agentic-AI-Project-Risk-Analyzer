tasks.csv         (required)  task_id,name,owner,start_date,due_date,est_days,progress,dependencies,priority,component
resources.csv     (optional)  name,role,capacity           <- capacity = concurrent tasks a person can comfortably handle (default 3)
issues.csv        (optional)  issue_id,task_id,severity,status,title
git_activity.csv  (optional)  task_id,commits_14d,last_commit_date

- dates: YYYY-MM-DD        - progress: 0-100          - dependencies: task ids separated by ";"  (e.g. T05;T07)
- priority: Low | Medium | High | Critical             - severity: Low | Medium | High | Critical
- status (issues): Open | Closed
Regenerate these samples for today's date with:  python -m projex.sample_data
