#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/launcher.sh"

action="${1:-menu}"

if [[ "$action" == "menu" ]]; then
  status="$($SCRIPT status)"
  echo "FruitSpy status: $status"
  echo "1) Start"
  echo "2) Stop"
  echo "3) Open Panel"
  echo "4) Exit"
  read "choice?Choose an action: "
  case "$choice" in
    1) $SCRIPT start; $SCRIPT open ;;
    2) $SCRIPT stop ;;
    3) $SCRIPT open ;;
    *) exit 0 ;;
  esac
else
  $SCRIPT "$action"
fi
