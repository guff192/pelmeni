#!/usr/bin/env bash

# Resolve project root (parent of this script's directory)
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

current_session=$(tmux display-message -p '#S')

# Create the three windows in the project directory
tmux new-window -n 'agent'  -t "$current_session:" -c "$project_dir"
tmux new-window -n 'editor' -t "$current_session:" -c "$project_dir"
tmux new-window -n 'shell'  -t "$current_session:" -c "$project_dir"

# Activate the virtual environment in all windows
tmux send-keys -t "$current_session:0"      'source ./.venv/bin/activate' Enter
tmux send-keys -t "$current_session:agent"  'source ./.venv/bin/activate' Enter
tmux send-keys -t "$current_session:editor" 'source ./.venv/bin/activate' Enter
tmux send-keys -t "$current_session:shell"  'source ./.venv/bin/activate' Enter

# Launch omp in the agent window and nvim in the editor window
tmux send-keys -t "$current_session:agent"  'omp' Enter
tmux send-keys -t "$current_session:editor" 'nvim' Enter
