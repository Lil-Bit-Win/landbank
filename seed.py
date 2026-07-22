"""
seed.py
Creates database tables (if they don't already exist, as a fallback to
migrations) and inserts seed data:
    - 1 admin user, 1 agent user (only if no users exist yet)
    - 2 example Knowledge Base articles (only if the table is empty)
    - 2 example SOPs (only if the table is empty)

Run once after setting up the database:
    python seed.py

Note: this replaces the old init_db.py from the pre-refactor version.
Prefer running migrations (flask db upgrade) to create the schema;
seed.py also calls db.create_all() as a safety net so it works even if
migrations haven't been run yet.
"""
import os

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.kb import KnowledgeBase
from app.models.sop import SOP

app = create_app()

with app.app_context():
    db.create_all()

    admin = None
    if User.query.count() == 0:
        admin = User(username="admin", role="admin")
        admin.set_password(os.environ.get("SEED_ADMIN_PASSWORD", "admin123"))

        agent = User(username="agent", role="agent")
        agent.set_password(os.environ.get("SEED_AGENT_PASSWORD", "agent123"))

        db.session.add_all([admin, agent])
        db.session.commit()
        print("Seeded users: admin/admin123 (role=admin), agent/agent123 (role=agent)")
    else:
        admin = User.query.filter_by(role="admin").first()

    if KnowledgeBase.query.count() == 0:
        kb_examples = [
            KnowledgeBase(
                title="No Dial Tone on Analog Telephone Line",
                description = "None",
                category="Telephone",
                problem=(
                    "Subscriber reports no dial tone on their analog telephone line. "
                    "Handset is confirmed working on another line."
                ),
                solution=(
                    "1. Check the physical line connection at the NID (Network Interface Device).\n"
                    "2. Verify voltage on the line using a multimeter (should read ~48V idle).\n"
                    "3. Inspect for water damage or corrosion in outdoor terminals.\n"
                    "4. If voltage is present but no dial tone, check the central office port assignment.\n"
                    "5. Swap the port on the DSLAM/switch if the issue persists.\n"
                    "6. Test with a known-good telephone set before closing the ticket."
                ),
                tags="telephone, dial tone, analog, no line, voltage",
                created_by=admin.id if admin else None,
            ),
            KnowledgeBase(
                title="Intermittent Internet Connection via DSL Router",
                description = "None",
                category="Router",
                problem="Customer reports internet connection drops every few minutes on a DSL router setup.",
                solution=(
                    "1. Check DSL sync status and line stability in the router admin page.\n"
                    "2. Inspect SNR (Signal-to-Noise Ratio) and line attenuation values.\n"
                    "3. Replace or re-seat the DSL filter/splitter at the customer premises.\n"
                    "4. Check for loose wiring at the NID and inside wiring.\n"
                    "5. Update router firmware if outdated.\n"
                    "6. If sync drops persist, escalate to line testing (MLT) for outside plant issues."
                ),
                tags="router, DSL, intermittent, disconnection, SNR",
                created_by=admin.id if admin else None,
            ),
        ]
        db.session.add_all(kb_examples)

    if SOP.query.count() == 0:
        sop_examples = [
            SOP(
                title="Handling Customer Line Trouble Reports",
                description = "None",
                purpose=(
                    "To standardize the process of receiving, diagnosing, and resolving "
                    "customer-reported line trouble to ensure consistent service quality."
                ),
                scope=(
                    "Applies to all CSU technicians and support staff handling incoming "
                    "telephone and internet trouble reports."
                ),
                procedure=(
                    "1. Log the trouble report with customer details and issue description.\n"
                    "2. Perform remote line diagnostics (voltage, sync, port status).\n"
                    "3. Determine if the issue is inside plant, outside plant, or customer premises equipment.\n"
                    "4. Dispatch a field technician if remote diagnostics are inconclusive.\n"
                    "5. Document findings and resolution in the ticketing system.\n"
                    "6. Confirm restoration of service with the customer before closing the ticket."
                ),
                responsible_person="CSU Support Technician / Field Technician",
                created_by=admin.id if admin else None,
            ),
            SOP(
                title="Router Configuration Backup and Restore",
                description = "None",
                purpose=(
                    "To ensure router configurations are properly backed up before changes "
                    "and can be restored quickly in case of failure."
                ),
                scope="Applies to all network routers and DSL/fiber CPE devices managed by the CSU.",
                procedure=(
                    "1. Access the router admin console using approved credentials.\n"
                    "2. Export the current configuration file and save it to the designated backup folder.\n"
                    "3. Label the backup file with device ID and date.\n"
                    "4. Before making any configuration changes, verify a recent backup exists.\n"
                    "5. In case of failure, restore the last known good configuration file.\n"
                    "6. Verify device functionality after restore and update the change log."
                ),
                responsible_person="Network Administrator",
                created_by=admin.id if admin else None,
            ),
        ]
        db.session.add_all(sop_examples)

    db.session.commit()
    print("Seed data ensured (Knowledge Base + SOP examples).")

    from app.services.permission_service import ensure_default_permissions
    ensure_default_permissions()
    print("Default permission mappings ensured (Feature 3 — RBAC+).")
