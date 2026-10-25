# How every headless Argon session runs Qwen Code; sourced by agent.sh and smoke.sh after they
# set $root.
#
# The settings live in the repo and are passed as Qwen Code's system settings, so they apply
# whichever directory a session runs in (set QWEN_CODE_SYSTEM_SETTINGS_PATH to use others). YOLO
# approves every tool call (headless mode has no one to ask); the excluded tools would let an
# unattended session schedule or park itself, or keep notes outside NOTES.md.
qwen_env=(
  QWEN_CODE_SYSTEM_SETTINGS_PATH="${QWEN_CODE_SYSTEM_SETTINGS_PATH:-$root/.qwen/settings.json}"
  QWEN_CODE_UNATTENDED_RETRY=1 # retry 429s and 529s instead of failing the session
  QWEN_CODE_SUPPRESS_YOLO_WARNING=1
)
qwen_flags=(--yolo --output-format stream-json)
for tool in cron_create cron_list cron_delete loop_wakeup enter_worktree exit_worktree \
  send_message record_artifact notebook_edit zoom_image report_findings manage_memory \
  search_memory; do
  qwen_flags+=(--exclude-tools "$tool")
done
