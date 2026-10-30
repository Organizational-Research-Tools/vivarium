
import pandas as pd
df = pd.read_csv('records.csv')
print("Columns:", df.columns.tolist())
print("Shape:", df.shape)
print()
# Show recent records with prototype info
print(df[['record_id','project_id','prototype_id','instrument','mean','module_02_secondary_sheet']].tail(30).to_string())
