"""Create demo users, the policy knowledge base, routing rules and realistic claims.

Claims with documents go through the real pipeline (extraction -> RAG -> checks -> routing),
so what you see in the app is produced by the system, not hard-coded.

    python manage.py seed_demo          # add demo data
    python manage.py seed_demo --reset  # wipe claims/policies/users (except superusers) first
"""
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from claims import services
from claims.demo_pdf import write_pdf
from claims.models import ApprovalStep, Claim, ClaimDocument, ClaimEvent, Payment, RoutingRule
from claims.verification.extraction import extract_document
from policies.models import Policy

PASSWORD = "Pass@123"
SAMPLES = Path(settings.BASE_DIR).parent / "sample_documents"


def d(n):
    return timezone.localdate() - timedelta(days=n)


def fmt(day):
    return day.strftime("%d/%m/%Y")


POLICIES = [
    dict(code="GEN-001", title="General reimbursement conditions", category="all", version=1, source="HR",
         effective_from=date(2025, 4, 1), text="""All business expenses must be supported by original invoices, bills or receipts that show the vendor, date, amount and the employee's name where applicable.

Expenses must be incurred for company business only. Personal expenses, alcohol, fines, penalties and late fees are not reimbursable.

An expense may be claimed only once. Splitting one bill across claims, or claiming the same invoice twice, is treated as a policy breach and is reported to HR.

Employees are responsible for the accuracy of the claim form. Differences between the form and the documents will delay approval."""),
    dict(code="TRV-ACC", title="Hotel accommodation policy", category="accommodation", version=1, source="HR",
         effective_from=date(2025, 4, 1), effective_to=date(2026, 3, 31), applicable_grades=["L1", "L2"],
         limit_amount=5000, limit_basis="per_night", required_documents=["invoice", "payment_proof"], submission_window_days=30,
         text="""Employees in grades L1 and L2 travelling on business may stay in hotels up to Rs. 5,000 per night including taxes.

The hotel tax invoice in the employee's name and proof of payment are required. Room upgrades, minibar and laundry are not reimbursable.

Claims must be submitted within 30 days of check-out."""),
    dict(code="TRV-ACC", title="Hotel accommodation policy", category="accommodation", version=2, source="HR",
         effective_from=date(2026, 4, 1), applicable_grades=["L1", "L2"],
         limit_amount=6000, limit_basis="per_night", required_documents=["invoice", "payment_proof"], submission_window_days=30,
         text="""From 1 April 2026, employees in grades L1 and L2 may stay in hotels up to Rs. 6,000 per night including taxes in all cities.

The hotel tax invoice in the employee's name and proof of payment are required. Room upgrades, minibar and laundry are not reimbursable.

Claims must be submitted within 30 days of check-out. Stays above the limit need written approval from the department head before travel."""),
    dict(code="TRV-ACC-SR", title="Hotel accommodation for senior staff", category="accommodation", version=1, source="HR",
         effective_from=date(2025, 4, 1), applicable_grades=["L3", "L4"],
         limit_amount=9000, limit_basis="per_night", required_documents=["invoice", "payment_proof"], submission_window_days=30,
         text="""Employees in grades L3 and L4 may stay in hotels up to Rs. 9,000 per night including taxes.

The hotel tax invoice and proof of payment are required. Claims must be submitted within 30 days of check-out."""),
    dict(code="FIN-CIR-07", title="Finance circular: revised metro hotel rates", category="accommodation", version=1, source="FINANCE",
         effective_from=date(2026, 7, 1), limit_amount=7500, limit_basis="per_night", required_documents=["invoice", "payment_proof"],
         text="""Finance circular 07/2026. Due to increased hotel tariffs in metro cities (Mumbai, Delhi, Bengaluru, Chennai, Hyderabad, Kolkata), the hotel limit for all grades is revised to Rs. 7,500 per night including taxes, effective 1 July 2026.

This circular applies until the HR travel policy is updated. Invoice and payment proof remain mandatory."""),
    dict(code="TRV-GEN", title="Business travel: air, rail and road", category="travel", version=1, source="HR",
         effective_from=date(2025, 4, 1), limit_amount=15000, limit_basis="per_claim", preapproval_above=10000,
         required_documents=["invoice", "payment_proof"], submission_window_days=30,
         text="""Economy air, AC rail and local cab or taxi travel for business purposes is reimbursable up to Rs. 15,000 per claim.

Tickets, invoices or ride receipts must be attached along with proof of payment.

Any single claim above Rs. 10,000 needs prior written approval from the reporting manager. Attach the approval email or form as an approval document.

Claims must be submitted within 30 days of travel."""),
    dict(code="FOOD-DA", title="Meals and daily allowance", category="food", version=1, source="HR",
         effective_from=date(2025, 4, 1), applicable_grades=["L1", "L2"], limit_amount=1000, limit_basis="per_day",
         required_documents=["bill"], submission_window_days=30,
         text="""Employees in grades L1 and L2 may claim meals during business travel or client meetings up to Rs. 1,000 per day.

An itemised restaurant bill is required. Alcohol is not reimbursable. Team meals need the names of attendees in the description."""),
    dict(code="FOOD-DA-SR", title="Meals allowance for senior staff", category="food", version=1, source="HR",
         effective_from=date(2025, 4, 1), applicable_grades=["L3", "L4"], limit_amount=1800, limit_basis="per_day",
         required_documents=["bill"], submission_window_days=30,
         text="""Employees in grades L3 and L4 may claim business meals up to Rs. 1,800 per day. An itemised bill is required."""),
    dict(code="MED-OPD", title="Outpatient medical reimbursement", category="medical", version=1, source="HR",
         effective_from=date(2025, 4, 1), limit_amount=25000, limit_basis="per_claim",
         required_documents=["medical_bill", "prescription"], submission_window_days=30,
         text="""Outpatient consultation, diagnostic tests and prescribed medicines are reimbursable up to Rs. 25,000 per claim for the employee.

A medical bill from a registered clinic, hospital or pharmacy and a doctor's prescription are both required.

Claims must be submitted within 30 days of the bill date. Medical claims are reviewed by HR for confidentiality."""),
    dict(code="OTH-MISC", title="Other business expenses", category="other", version=1, source="ADMIN",
         effective_from=date(2025, 4, 1), limit_amount=3000, limit_basis="per_claim", required_documents=["invoice", "approval"],
         submission_window_days=45,
         text="""Other business expenses such as conference fees, courier, stationery and printing are reimbursable up to Rs. 3,000 per claim.

An invoice and the manager's prior approval are required for every claim in this category."""),
]

RULES = [
    dict(name="High-value claims (₹25,000 and above)", condition="amount_gte", value="25000", add_role="DEPT_HEAD"),
    dict(name="Risk score 60 or more", condition="risk_gte", value="60", add_role="DEPT_HEAD"),
    dict(name="Possible duplicate detected", condition="has_finding", value="DUPLICATE", add_role="DEPT_HEAD"),
    dict(name="Medical claims are reviewed by HR", condition="category_is", value="medical", add_role="HR"),
    dict(name="Policy conflicts need HR clarification", condition="has_finding", value="CONFLICT", add_role="HR"),
]


class Command(BaseCommand):
    help = "Load demo users, policies, routing rules and claims"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first")

    def handle(self, *args, **opts):
        random.seed(7)
        if opts["reset"]:
            for doc in ClaimDocument.objects.all():
                doc.file.delete(save=False)
            Claim.objects.all().delete()
            Policy.objects.all().delete()
            RoutingRule.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write("Cleared existing data.")

        SAMPLES.mkdir(parents=True, exist_ok=True)
        self.users = self.make_users()
        self.make_policies()
        for rule in RULES:
            RoutingRule.objects.get_or_create(name=rule["name"], defaults=rule)
        if Claim.objects.exists():
            self.stdout.write(self.style.WARNING("Claims already exist; skipping demo claims. Use --reset to rebuild."))
        else:
            self.make_history()
            self.make_live_claims()
            self.make_try_it_samples()
        self.stdout.write(self.style.SUCCESS(f"Demo ready. Every demo account uses the password {PASSWORD}"))
        for u in User.objects.exclude(is_superuser=True).order_by("role"):
            self.stdout.write(f"  {u.username:<16} {u.get_role_display():<16} {u.full_name}")

    # ------------------------------------------------------------------ people
    def make_users(self):
        spec = [
            ("admin", "Asha", "Menon", "ADMIN", "L4", "Administration", "System administrator", "E0001", None),
            ("priya.finance", "Priya", "Nair", "FINANCE", "L3", "Finance", "Accounts payable lead", "E0102", None),
            ("meera.hr", "Meera", "Krishnan", "HR", "L3", "Human Resources", "HR business partner", "E0145", None),
            ("arjun.head", "Arjun", "Mehta", "DEPT_HEAD", "L4", "Engineering", "Head of engineering", "E0011", None),
            ("ravi.manager", "Ravi", "Shankar", "MANAGER", "L3", "Engineering", "Engineering manager", "E0034", "arjun.head"),
            ("vikram.manager", "Vikram", "Das", "MANAGER", "L3", "Sales", "Regional sales manager", "E0051", "arjun.head"),
            ("ananya", "Ananya", "Rao", "EMPLOYEE", "L2", "Engineering", "Senior software engineer", "E1021", "ravi.manager"),
            ("karthik", "Karthik", "Subramanian", "EMPLOYEE", "L1", "Engineering", "Software engineer", "E1088", "ravi.manager"),
            ("sneha", "Sneha", "Iyer", "EMPLOYEE", "L2", "Sales", "Account executive", "E1102", "vikram.manager"),
        ]
        users = {}
        for username, first, last, role, grade, dept, title, emp_id, manager in spec:
            user, created = User.objects.get_or_create(username=username, defaults=dict(
                first_name=first, last_name=last, role=role, grade=grade, department=dept, designation=title,
                employee_id=emp_id, email=f"{username.split('.')[0]}@claimlens.test", is_staff=role == "ADMIN",
                is_superuser=False,
            ))
            if created:
                user.set_password(PASSWORD)
                user.save()
            users[username] = user
        for username, *_rest, manager in spec:
            if manager and not users[username].manager_id:
                users[username].manager = users[manager]
                users[username].save(update_fields=["manager"])
        admin = users["admin"]
        if not admin.is_staff:
            admin.is_staff = True
            admin.save(update_fields=["is_staff"])
        return users

    def make_policies(self):
        for spec in POLICIES:
            spec = dict(spec)
            Policy.objects.get_or_create(code=spec.pop("code"), version=spec.pop("version"), defaults=spec)

    # ---------------------------------------------------------------- helpers
    def pdf(self, name, blocks):
        return write_pdf(SAMPLES / name, blocks)

    def new_claim(self, username, **fields):
        claim = Claim.objects.create(employee=self.users[username], status=Claim.Status.DRAFT, **fields)
        services.log(claim, claim.employee, "CREATED", "Draft claim created")
        return claim

    def attach(self, claim, path, doc_type):
        path = Path(path)
        with open(path, "rb") as fh:
            doc = ClaimDocument(claim=claim, doc_type=doc_type, original_name=path.name, size=path.stat().st_size, uploaded_by=claim.employee)
            doc.file.save(path.name, File(fh), save=True)
        extract_document(doc)
        services.log(claim, claim.employee, "DOCUMENT_UPLOADED", f"Uploaded {doc.get_doc_type_display().lower()}: {path.name}")
        return doc

    def decide(self, claim, action, comment="", amount=None):
        step = claim.current_step()
        actor = step.approver or User.objects.filter(role=step.role).first()
        return services.act(claim, actor, action, comment, amount)

    def backdate(self, claim, days):
        Claim.objects.filter(pk=claim.pk).update(submitted_at=timezone.now() - timedelta(days=days))
        claim.refresh_from_db()

    # ----------------------------------------------------------- live claims
    def make_live_claims(self):
        finance = self.users["priya.finance"]

        # 1. Ananya: Mumbai hotel, over the per-night limit, form amount differs, HR/Finance rules conflict
        cin, cout = d(19), d(17)
        hotel = self.pdf("orchid_residency_invoice.pdf", [
            ("h1", "The Orchid Residency"), ("small", "Nariman Point, Mumbai 400021"), ("small", "GSTIN: 27AABCO1234F1Z5"), ("gap", ""),
            ("h2", "TAX INVOICE"), ("rule", ""),
            ("text", f"Invoice No: HTL-{cout.year}-0458"), ("text", f"Invoice Date: {fmt(cout)}"),
            ("text", "Guest Name: Ananya Rao"), ("text", f"Check-in: {fmt(cin)}"), ("text", f"Check-out: {fmt(cout)}"),
            ("text", "Room: Deluxe King, 2 nights"), ("rule", ""),
            ("row", ("Room tariff 2 x Rs. 5,800.00", "11,600.00")), ("row", ("CGST 6%", "696.00")), ("row", ("SGST 6%", "696.00")),
            ("rule", ""), ("row", ("Grand Total Rs.", "12,992.00")), ("gap", ""), ("small", "Paid by UPI. Thank you for staying with us."),
        ])
        upi = self.pdf("orchid_upi_payment.pdf", [
            ("h1", "Payment successful"), ("text", "Paid to: The Orchid Residency"), ("text", "Amount Paid: Rs. 12,992.00"),
            ("text", "UPI Ref No: 426817390021"), ("text", f"Payment Date: {fmt(cout)}"), ("text", "From: Ananya Rao (HDFC Bank)"),
        ])
        c1 = self.new_claim("ananya", category="accommodation", title="Hotel stay for client workshop in Mumbai",
                            description="Two nights at The Orchid Residency for the Axis client discovery workshop.",
                            amount=Decimal("13500"), expense_date=cout, start_date=cin, end_date=cout,
                            vendor="The Orchid Residency", invoice_number=f"HTL-{cout.year}-0458", city="Mumbai")
        self.attach(c1, hotel, "invoice")
        self.attach(c1, upi, "payment_proof")
        services.submit(c1, c1.employee)
        self.backdate(c1, 2)

        # 2. Ananya: clean team dinner -> approved -> paid
        dinner_day = d(12)
        bill = self.pdf("toit_dinner_bill.pdf", [
            ("h1", "Toit Brewpub"), ("small", "Indiranagar, Bengaluru"), ("h2", "Bill"), ("rule", ""),
            ("text", "Bill No: TB-88213"), ("text", f"Date: {fmt(dinner_day)}"), ("text", "Table 14, 3 guests"), ("rule", ""),
            ("row", ("Paneer tikka", "320.00")), ("row", ("Veg biryani x 2", "440.00")), ("row", ("Fresh lime soda x 3", "90.00")),
            ("rule", ""), ("row", ("Total Rs.", "850.00")),
        ])
        c2 = self.new_claim("ananya", category="food", title="Client lunch with Axis team",
                            description="Lunch with Rohan and Divya from Axis after the requirements session.",
                            amount=Decimal("850"), expense_date=dinner_day, vendor="Toit Brewpub", invoice_number="TB-88213", city="Bengaluru")
        self.attach(c2, bill, "bill")
        services.submit(c2, c2.employee)
        self.backdate(c2, 11)
        self.decide(c2, "approve", "Fine.")
        self.decide(c2, "approve", "Verified against bill.")
        services.initiate_payment(c2, finance, "bank_transfer")
        services.complete_payment(c2, finance, "NEFT-HDFC-7781203")

        # 3. Karthik: flight above pre-approval threshold, no approval attached; manager approved, waiting on Finance
        fly = d(9)
        ticket = self.pdf("indigo_eticket.pdf", [
            ("h1", "IndiGo"), ("h2", "e-Ticket and booking confirmation"), ("rule", ""),
            ("text", "PNR: X7K2QM"), ("text", "Passenger Name: Karthik Subramanian"), ("text", f"Date of Journey: {fmt(fly)}"),
            ("text", "6E 2134  BLR 06:10  ->  DEL 08:55"), ("text", "6E 2135  DEL 19:30  ->  BLR 22:15"), ("rule", ""),
            ("row", ("Base fare", "10,480.00")), ("row", ("Taxes and fees", "1,920.00")), ("rule", ""), ("row", ("Total Fare Rs.", "12,400.00")),
        ])
        pay3 = self.pdf("indigo_card_payment.pdf", [
            ("h1", "Transaction receipt"), ("text", "Paid to: InterGlobe Aviation (IndiGo)"), ("text", "Amount Paid: Rs. 12,400.00"),
            ("text", "Transaction ID: TXN98231776"), ("text", f"Date: {fmt(fly - timedelta(days=6))}"),
        ])
        c3 = self.new_claim("karthik", category="travel", title="Flights to Delhi for vendor audit",
                            description="Same-day return trip to audit the data centre vendor in Gurugram.",
                            amount=Decimal("12400"), expense_date=fly, start_date=fly, end_date=fly,
                            vendor="IndiGo", invoice_number="X7K2QM", city="Delhi")
        self.attach(c3, ticket, "ticket")
        self.attach(c3, pay3, "payment_proof")
        services.submit(c3, c3.employee)
        self.backdate(c3, 6)
        self.decide(c3, "approve", "Trip was approved verbally in sprint planning.")

        # 4. Karthik: re-uses Ananya's hotel invoice -> duplicate + name mismatch
        c4 = self.new_claim("karthik", category="accommodation", title="Hotel in Mumbai",
                            description="Stay during client workshop.", amount=Decimal("12992"), expense_date=cout,
                            start_date=cin, end_date=cout, vendor="The Orchid Residency", invoice_number=f"HTL-{cout.year}-0458", city="Mumbai")
        self.attach(c4, hotel, "invoice")
        services.submit(c4, c4.employee)
        self.backdate(c4, 1)

        # 5. Sneha: medical bill without prescription -> HR route; manager asks for documents
        med_day = d(8)
        med = self.pdf("apollo_clinic_bill.pdf", [
            ("h1", "Apollo Clinic"), ("small", "Koramangala, Bengaluru"), ("h2", "OPD Bill"), ("rule", ""),
            ("text", "Bill No: APC-55120"), ("text", "Patient Name: Sneha Iyer"), ("text", f"Bill Date: {fmt(med_day)}"), ("rule", ""),
            ("row", ("Consultation, Dr. N. Hegde", "800.00")), ("row", ("Blood panel", "3,400.00")), ("rule", ""),
            ("row", ("Net Amount Rs.", "4,200.00")),
        ])
        c5 = self.new_claim("sneha", category="medical", title="Doctor consultation and blood tests",
                            amount=Decimal("4200"), expense_date=med_day, vendor="Apollo Clinic", invoice_number="APC-55120", city="Bengaluru")
        self.attach(c5, med, "medical_bill")
        services.submit(c5, c5.employee)
        self.backdate(c5, 5)
        self.decide(c5, "request_documents", "Please attach the doctor's prescription, it's required by MED-OPD.")

        # 6. Sneha: cab rides approved, payment overdue
        cab_day = d(20)
        cab = self.pdf("uber_trip_receipts.pdf", [
            ("h1", "Uber"), ("h2", "Trip receipts summary"), ("rule", ""), ("text", "Receipt No: UBR-2290-4471"),
            ("text", "Rider Name: Sneha Iyer"), ("text", f"Date: {fmt(cab_day)}"), ("rule", ""),
            ("row", ("Office to Whitefield client site", "640.00")), ("row", ("Whitefield to MG Road", "580.00")),
            ("row", ("MG Road to office", "630.00")), ("rule", ""), ("row", ("Total Rs.", "1,850.00")),
        ])
        cabpay = self.pdf("uber_upi_payment.pdf", [
            ("h1", "Payment successful"), ("text", "Paid to: Uber India"), ("text", "Amount Paid: Rs. 1,850.00"),
            ("text", "UPI Ref No: 518822904417"), ("text", f"Date: {fmt(cab_day)}"),
        ])
        c6 = self.new_claim("sneha", category="travel", title="Cab rides for client visits in Whitefield",
                            amount=Decimal("1850"), expense_date=cab_day, start_date=cab_day, end_date=cab_day,
                            vendor="Uber", invoice_number="UBR-2290-4471", city="Bengaluru")
        self.attach(c6, cab, "receipt")
        self.attach(c6, cabpay, "payment_proof")
        services.submit(c6, c6.employee)
        self.decide(c6, "approve")
        self.decide(c6, "approve", "OK to pay.")
        Claim.objects.filter(pk=c6.pk).update(submitted_at=timezone.now() - timedelta(days=17), decided_at=timezone.now() - timedelta(days=14))
        Payment.objects.filter(claim=c6).update(due_date=d(7))

        # 7. Karthik: conference fee without approval -> rejected
        conf_day = d(25)
        conf = self.pdf("pycon_registration_invoice.pdf", [
            ("h1", "PyCon India"), ("h2", "Registration invoice"), ("rule", ""), ("text", "Invoice No: PCI-26-10293"),
            ("text", "Name: Karthik Subramanian"), ("text", f"Invoice Date: {fmt(conf_day)}"), ("rule", ""),
            ("row", ("Conference pass (professional)", "2,500.00")), ("rule", ""), ("row", ("Total Rs.", "2,500.00")),
        ])
        c7 = self.new_claim("karthik", category="other", title="PyCon India registration", amount=Decimal("2500"),
                            expense_date=conf_day, vendor="PyCon India", invoice_number="PCI-26-10293", city="Bengaluru")
        self.attach(c7, conf, "invoice")
        services.submit(c7, c7.employee)
        self.decide(c7, "reject", "Conference wasn't pre-approved. Please raise a training request first.")

        # 8. Ananya: draft
        self.new_claim("ananya", category="travel", title="Airport cab", amount=Decimal("780"), expense_date=d(1), vendor="Ola", city="Bengaluru")

    # ------------------------------------------------------ settled history
    def make_history(self):
        """Older settled/rejected claims so analytics has six months of data (no documents attached)."""
        finance = self.users["priya.finance"]
        employees = [self.users[u] for u in ("ananya", "karthik", "sneha", "ravi.manager", "vikram.manager")]
        templates = [
            ("food", "Team lunch", 600, 980), ("travel", "Cab to client office", 300, 1400), ("travel", "Train to Chennai", 900, 2400),
            ("accommodation", "Hotel in Hyderabad", 4200, 5900), ("other", "Courier charges", 250, 900), ("medical", "Pharmacy bill", 400, 2600),
        ]
        for i in range(26):
            days_ago = random.randint(35, 175)
            cat, title, lo, hi = random.choice(templates)
            emp = random.choice(employees)
            submitted = timezone.now() - timedelta(days=days_ago)
            claim = Claim.objects.create(
                employee=emp, category=cat, title=title, amount=Decimal(random.randrange(lo, hi, 10)),
                expense_date=timezone.localdate(submitted) - timedelta(days=random.randint(1, 6)), vendor="Various",
                status=Claim.Status.PAID, review_round=1, risk_score=random.choice([0, 4, 8, 12, 16, 28]),
                submitted_at=submitted, decided_at=submitted + timedelta(hours=random.randint(10, 90)),
                verification_level="Level 1: Manager → Finance", ai_recommendation="approve",
                verification_summary="All checks passed at the time of review.",
            )
            claim.risk_level = "medium" if claim.risk_score >= 20 else "low"
            outcome = random.random()
            if outcome < 0.15:
                claim.status = Claim.Status.REJECTED
                claim.save()
                ClaimEvent.objects.create(claim=claim, actor=emp.manager, action="REJECTED", message="Rejected: personal expense.")
                continue
            claim.approved_amount = claim.amount
            claim.save()
            paid_at = claim.decided_at + timedelta(days=random.randint(2, 11))
            Payment.objects.create(
                claim=claim, approved_amount=claim.amount, status=Payment.Status.PAID, method="bank_transfer",
                due_date=timezone.localdate(claim.decided_at) + timedelta(days=settings.CLAIMS["PAYMENT_PERIOD_DAYS"]),
                initiated_at=paid_at - timedelta(days=1), initiated_by=finance, paid_at=paid_at,
                reference_number=f"NEFT-{random.randint(1000000, 9999999)}",
            )
            for seq, role in enumerate(["MANAGER", "FINANCE"], 1):
                ApprovalStep.objects.create(claim=claim, round=1, sequence=seq, role=role, status="APPROVED",
                                            approver=emp.manager if role == "MANAGER" else finance,
                                            acted_by=emp.manager if role == "MANAGER" else finance, acted_at=claim.decided_at)
            ClaimEvent.objects.create(claim=claim, actor=finance, action="PAID", message=f"Settled with reference {claim.payment.reference_number}.")

    def make_try_it_samples(self):
        """Fresh documents you can upload yourself while logged in as Ananya."""
        day = d(3)
        self.pdf("try_it_food_bill.pdf", [
            ("h1", "Meghana Foods"), ("small", "Residency Road, Bengaluru"), ("h2", "Bill"), ("rule", ""),
            ("text", "Bill No: MF-40917"), ("text", f"Date: {fmt(day)}"), ("rule", ""),
            ("row", ("Chicken biryani", "380.00")), ("row", ("Paneer butter masala", "260.00")), ("rule", ""), ("row", ("Total Rs.", "640.00")),
        ])
        self.pdf("try_it_food_payment.pdf", [
            ("h1", "Payment successful"), ("text", "Paid to: Meghana Foods"), ("text", "Amount Paid: Rs. 640.00"),
            ("text", "UPI Ref No: 611093842210"), ("text", f"Date: {fmt(day)}"), ("text", "From: Ananya Rao"),
        ])
        (SAMPLES / "README.txt").write_text(
            "Sample documents generated by `python manage.py seed_demo`.\n\n"
            f"try_it_food_bill.pdf: log in as ananya, create a Food claim for Rs. 640 dated {day:%d %b %Y} with vendor Meghana Foods,\n"
            "invoice number MF-40917, upload the bill as 'Bill' and submit. It should pass cleanly.\n"
            "Change the amount to 1,500 to see a policy violation and an amount mismatch.\n\n"
            "orchid_residency_invoice.pdf: upload it in any new accommodation claim to see duplicate detection.\n",
            encoding="utf-8",
        )
