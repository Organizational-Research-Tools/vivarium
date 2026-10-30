
import pandas as pd
df = pd.read_csv('records.csv')
print("Columns:", df.columns.tolist())
print("Total records:", len(df))
print()
# Show water panel records from recent sessions
water = df[df['instrument'] == 'water'].copy()
print("Recent water records (kind=panel):")
panels = water[water['kind'] == 'panel']
print(panels[['record_id','project','prototype','value']].tail(30).to_string())
