"""Test script to verify crash data direction handling"""
import pandas as pd
import sys
sys.path.insert(0, '.')
from aggregate_inrix import _read_crash_csv

print("="*60)
print("CRASH DATA DIRECTION HANDLING TEST")
print("="*60)

# Load crash data
crash_df = _read_crash_csv('crash_data_2022.csv')

print("\nCrash Data Loaded:")
print(crash_df)

print(f"\nColumns: {list(crash_df.columns)}")
print(f"\nHas direction column: {'direction' in crash_df.columns}")

if 'direction' in crash_df.columns:
    print(f"\nDirections found: {sorted(crash_df['direction'].unique())}")
    print(f"\nCrashes by direction:")
    for direction in sorted(crash_df['direction'].unique()):
        dir_crashes = crash_df[crash_df['direction'] == direction]
        print(f"  {direction}: {len(dir_crashes)} event(s)")
        for idx, row in dir_crashes.iterrows():
            print(f"    - {row['date'].strftime('%Y-%m-%d')}")
else:
    print("\nNo direction column found (will merge to all directions)")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
