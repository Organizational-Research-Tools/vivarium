import pandas as pd
df = pd.read_csv('records.csv')
# Check p_P68BNAVWAV water panel mean
wav_water = df[df['prototype_id']=='p_P68BNAVWAV']
print("p_P68BNAVWAV water panel:")
print(wav_water[['record_id','test','value','measured_by']])
print(f"Mean: {wav_water['value'].mean():.3f}%")
print()
# p_02A6NY9WNR = 5BU heat panel
print("p_02A6NY9WNR (5BU) heat panel:")
h02a = df[df['prototype_id']=='p_02A6NY9WNR']
print(h02a[['record_id','test','value']])
print(f"Mean: {h02a['value'].mean():.3f}°C = {(h02a['value'].mean()-77.5)/0.25:.2f} steps")
