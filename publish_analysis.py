from pathlib import Path
from decimal import Decimal
from analyze import run
from collect import Sink

report=run(Path("sample-data"),Decimal("1"))
sink=Sink("report-checkpoint",True)
sink.write("reports/latest.json",report)
sink.flush()
print("Published paper-analysis report; inspect coverage before interpreting rankings.")
