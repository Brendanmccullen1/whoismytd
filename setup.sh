#!/bin/bash

set -e

echo "========================================"
echo "whoismytd.ie Database Setup"
echo "========================================"
echo ""

# Check if Docker is running
if ! docker ps > /dev/null 2>&1; then
    echo "❌ Docker is not running."
    echo "   Please start Docker Desktop and try again."
    exit 1
fi

echo "✓ Docker is running"
echo ""

# Start Postgres
echo "Starting PostgreSQL container..."
docker compose up -d

echo "Waiting for Postgres to be ready..."
sleep 5

# Check Postgres is ready
if docker compose exec -T db pg_isready -U whoismytd > /dev/null 2>&1; then
    echo "✓ PostgreSQL is ready"
else
    echo "⏳ Waiting a bit longer..."
    sleep 5
fi

echo ""
echo "========================================"
echo "Populating database..."
echo "========================================"
echo ""

# Activate venv and run populate
source venv/bin/activate
python populate.py

echo ""
echo "========================================"
echo "✓ Setup complete!"
echo "========================================"
echo ""
echo "To inspect the data:"
echo "  psql \$DATABASE_URL"
echo ""
echo "Example queries:"
echo "  SELECT COUNT(*) FROM members;"
echo "  SELECT COUNT(*) FROM divisions;"
echo "  SELECT m.full_name, COUNT(*) as vote_count"
echo "    FROM member_votes mv"
echo "    JOIN members m ON m.id = mv.member_id"
echo "    GROUP BY m.full_name ORDER BY vote_count DESC LIMIT 10;"
echo ""
