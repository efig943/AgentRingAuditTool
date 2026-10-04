#!/bin/bash
# Startup script for CallAudit Pro Production Support Dashboard & Daemon
cd "$(dirname "$0")"

echo "=========================================================="
echo "🚀 Starting CallAudit Pro - Production Support Voice Auditor"
echo "=========================================================="
echo "📍 Dashboard URL: http://localhost:5050"
echo "📧 Alert Recipient: ethan.figueredo943@gmail.com"
echo "⚡ Gemini Engine: gemini-3.8-flash"
echo "🗄️ PostgreSQL Database: Supabase (aws-1-us-east-2.pooler.supabase.com)"
echo "=========================================================="

python3 server.py
