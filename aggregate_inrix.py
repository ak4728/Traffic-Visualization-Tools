"""aggregate_inrix.py

Utilities to load INRIX-style travel-time CSVs and aggregate by corridor
and direction. Includes clustering analysis for daily travel patterns.
Single-file module, no outputs written. If plotting is requested, figures 
are shown then closed (no files saved).

Usage example (from command line or import):
    from aggregate_inrix import aggregate_travel_times, cluster_daily_patterns
    agg = aggregate_travel_times(cluster_csv, tmc_csv, corridors=..., resample='15min')
    clusters = cluster_daily_patterns(cluster_csv, tmc_csv, direction='EB', n_clusters=6)

"""
from typing import Dict, List, Optional, Tuple
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score


def filter_data(
    df: pd.DataFrame,
    day_of_week: Optional[int] = None,
    start_hour: Optional[int] = None,
    end_hour: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> pd.DataFrame:
    """Filter DataFrame by temporal criteria.
    
    Parameters:
    - df: DataFrame with 'datetime' column
    - day_of_week: filter to specific day (0=Monday, 1=Tuesday, 2=Wednesday, etc.)
                   None = all days
    - start_hour: start hour (inclusive), 0-23. None = no filter
    - end_hour: end hour (exclusive), 0-24. None = no filter
    - start_date: start date string 'YYYY-MM-DD'. None = no filter
    - end_date: end date string 'YYYY-MM-DD'. None = no filter
    
    Returns:
    - Filtered DataFrame
    """
    filtered = df.copy()
    
    # Add temporal columns if not present
    if 'day_of_week' not in filtered.columns:
        filtered['day_of_week'] = filtered['datetime'].dt.dayofweek
    if 'hour' not in filtered.columns:
        filtered['hour'] = filtered['datetime'].dt.hour
    
    # Apply filters
    if day_of_week is not None:
        filtered = filtered[filtered['day_of_week'] == day_of_week]
    
    if start_hour is not None:
        filtered = filtered[filtered['hour'] >= start_hour]
    
    if end_hour is not None:
        filtered = filtered[filtered['hour'] < end_hour]
    
    if start_date is not None:
        filtered = filtered[filtered['datetime'] >= pd.to_datetime(start_date)]
    
    if end_date is not None:
        filtered = filtered[filtered['datetime'] <= pd.to_datetime(end_date)]
    
    return filtered


def _detect_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    # case-insensitive
    cols_lower = {col.lower(): col for col in df.columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return None


def _read_cluster_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # detect typical columns
    time_col = _detect_column(df, ['measurement_tstamp', 'DATE_TIME', 'Time', 'StartTime', 'Timestamp'])
    tmc_col = _detect_column(df, ['tmc_code', 'TMC', 'Tmc', 'tmc'])
    travel_col = _detect_column(df, ['travel_time_seconds', 'Travel Time', 'TravelTime', 'TT', 'travel_time', 'Travel_Time'])
    speed_col = _detect_column(df, ['speed', 'Speed', 'average_speed'])

    if time_col is None:
        raise ValueError('Could not find a datetime column in cluster CSV')
    if tmc_col is None:
        raise ValueError('Could not find a TMC id column in cluster CSV')
    if travel_col is None:
        raise ValueError('Could not find a travel-time column in cluster CSV')

    df[time_col] = pd.to_datetime(df[time_col])
    rename_dict = {time_col: 'datetime', tmc_col: 'tmc', travel_col: 'travel_time'}
    cols_to_keep = ['datetime', 'tmc', 'travel_time']
    
    if speed_col is not None:
        rename_dict[speed_col] = 'speed'
        cols_to_keep.append('speed')
    
    df = df.rename(columns=rename_dict)
    return df[cols_to_keep].copy()


def _read_tmc_csv(path: str) -> pd.DataFrame:
    """Read TMC identification CSV with date ranges for temporal matching.
    
    Returns DataFrame with active_start_date and active_end_date converted to datetime.
    """
    df = pd.read_csv(path)
    tmc_col = _detect_column(df, ['tmc', 'TMC', 'Tmc', 'tmc_code'])
    dir_col = _detect_column(df, ['direction', 'Direction', 'Dir', 'TravelDir'])
    name_col = _detect_column(df, ['road', 'Corridor', 'RoadName', 'NAME', 'Name'])
    order_col = _detect_column(df, ['road_order', 'order', 'sequence'])
    start_col = _detect_column(df, ['active_start_date', 'start_date', 'ActiveStartDate'])
    end_col = _detect_column(df, ['active_end_date', 'end_date', 'ActiveEndDate'])

    if tmc_col is None:
        raise ValueError('Could not find a TMC id column in TMC identification CSV')

    out = df[[tmc_col]].copy()
    out.columns = ['tmc']
    if dir_col is not None:
        out['direction'] = df[dir_col]
    if name_col is not None:
        out['corridor'] = df[name_col]
    if order_col is not None:
        out['road_order'] = df[order_col]
    
    # Add date range columns for temporal matching 
    # Strip timezone info to match with measurement timestamps (which are timezone-naive)
    if start_col is not None:
        start_dates = pd.to_datetime(df[start_col])
        # Remove timezone by keeping local time
        out['active_start_date'] = start_dates.apply(lambda x: x.replace(tzinfo=None) if pd.notna(x) and hasattr(x, 'replace') else x)
    if end_col is not None:
        end_dates = pd.to_datetime(df[end_col])
        # Remove timezone by keeping local time
        out['active_end_date'] = end_dates.apply(lambda x: x.replace(tzinfo=None) if pd.notna(x) and hasattr(x, 'replace') else x)
        # Handle NaT (current/ongoing segments) by setting to far future
        out['active_end_date'] = out['active_end_date'].fillna(pd.Timestamp('2099-12-31'))
    
    return out


def _merge_with_tmc_dates(data_df: pd.DataFrame, tmc_df: pd.DataFrame) -> pd.DataFrame:
    """Merge data with TMC metadata, matching on date ranges to avoid duplicates.
    
    Parameters:
    - data_df: DataFrame with 'datetime' and 'tmc' columns
    - tmc_df: TMC DataFrame with 'tmc', 'active_start_date', 'active_end_date'
    
    Returns:
    - Merged DataFrame with one row per (datetime, tmc) pair
    """
    # First merge to get all combinations
    merged = data_df.merge(tmc_df, on='tmc', how='left')
    
    # Filter to keep only rows where datetime falls within active date range
    if 'active_start_date' in merged.columns and 'active_end_date' in merged.columns:
        valid_mask = (
            (merged['datetime'] >= merged['active_start_date']) &
            (merged['datetime'] <= merged['active_end_date'])
        )
        merged = merged[valid_mask].copy()
        # Drop the date range columns as they're no longer needed
        merged = merged.drop(columns=['active_start_date', 'active_end_date'], errors='ignore')
    
    return merged


def aggregate_travel_times(
    cluster_csv: str,
    tmc_csv: Optional[str] = None,
    corridors: Optional[Dict[str, List[str]]] = None,
    direction: Optional[str] = None,
    resample: str = '15T',
    agg: str = 'median',
    travel_time_units: str = 'seconds',
    include_speed: bool = True
) -> pd.DataFrame:
    """Load cluster travel-time CSV and aggregate by corridor.

    Parameters:
    - cluster_csv: path to I70-ROD2-Cluster-Travel-Time.csv (INRIX-like)
    - tmc_csv: optional path to TMC_Identification.csv (provides direction/corridor)
    - corridors: optional mapping {corridor_name: [tmc_id, ...]} to define groups
    - direction: optional string to filter ('EB','WB','NB','SB', etc.) if available
    - resample: pandas offset alias for resampling e.g. '15T','1H'
    - agg: aggregation function name for group (median, mean, etc.)
    - travel_time_units: units in cluster CSV ('seconds' or 'minutes'); result is minutes
    - include_speed: whether to include speed data in aggregation (default True)

    Returns a DataFrame indexed by datetime with columns for each corridor's travel_time and speed.
    """
    df = _read_cluster_csv(cluster_csv)

    if travel_time_units.lower().startswith('s'):
        df['travel_time_min'] = df['travel_time'] / 60.0
    else:
        df['travel_time_min'] = df['travel_time']

    # attach tmc meta if provided
    if tmc_csv is not None:
        tdf = _read_tmc_csv(tmc_csv)
        df = _merge_with_tmc_dates(df, tdf)
    else:
        df['direction'] = None
        df['corridor'] = None

    # If corridors mapping provided, create a reverse map tmc->corridor
    if corridors is not None:
        rev = {}
        for cname, tlist in corridors.items():
            for t in tlist:
                rev[str(t)] = cname
        df['corridor'] = df['tmc'].astype(str).map(rev).fillna(df.get('corridor'))

    # Create corridor identifier combining road + direction if both exist
    if 'corridor' in df.columns and 'direction' in df.columns:
        has_corridor = df['corridor'].notna()
        has_direction = df['direction'].notna()
        both = has_corridor & has_direction
        if both.any():
            df.loc[both, 'corridor'] = df.loc[both, 'corridor'] + ' ' + df.loc[both, 'direction']
    
    # Optionally filter by direction
    if direction is not None:
        # match case-insensitive, if direction col exists
        if 'direction' in df.columns and df['direction'].notna().any():
            # Handle abbreviations: EB->EASTBOUND, WB->WESTBOUND, NB->NORTHBOUND, SB->SOUTHBOUND
            dir_map = {'EB': 'EASTBOUND', 'WB': 'WESTBOUND', 'NB': 'NORTHBOUND', 'SB': 'SOUTHBOUND'}
            search_dir = dir_map.get(direction.upper(), direction.upper())
            df = df[df['direction'].astype(str).str.upper().str.contains(search_dir)]

    # If no corridor assignment, fall back to using TMC id as corridor
    if 'corridor' not in df.columns or df['corridor'].isna().all():
        df['corridor'] = df['tmc'].astype(str)

    # set datetime index and resample
    df = df.set_index('datetime')

    # group by corridor, resample, aggregate
    has_speed = 'speed' in df.columns and include_speed
    
    def _agg_group(g):
        agg_dict = {}
        tt = getattr(g['travel_time_min'].resample(resample), agg)()
        agg_dict['travel_time'] = tt
        if has_speed:
            spd = getattr(g['speed'].resample(resample), agg)()
            agg_dict['speed'] = spd
        return pd.DataFrame(agg_dict)

    grouped = df.groupby('corridor')
    pieces = []
    for name, g in grouped:
        corridor_df = _agg_group(g)
        # rename columns to include corridor name
        corridor_df.columns = [f"{name}_{col}" for col in corridor_df.columns]
        pieces.append(corridor_df)

    if not pieces:
        return pd.DataFrame()

    result = pd.concat(pieces, axis=1).sort_index()
    return result


def _calculate_wcv_bcv_ratio(data: np.ndarray, labels: np.ndarray, feature_col_idx: int = 0) -> float:
    """Calculate Within Cluster Variance / Between Cluster Variance ratio.
    
    Lower values indicate better clustering (compact clusters, well-separated).
    
    Parameters:
    - data: Daily statistics array (n_days × n_features)
    - labels: Cluster labels for each day
    - feature_col_idx: Index of feature to use (0=avg_travel_time by default)
    
    Returns:
    - WCV/BCV ratio
    """
    feature_values = data[:, feature_col_idx]
    overall_mean = np.mean(feature_values)
    
    unique_labels = np.unique(labels)
    n_clusters = len(unique_labels)
    
    # Within-cluster variance (WCV)
    wcv = 0.0
    for label in unique_labels:
        cluster_data = feature_values[labels == label]
        cluster_mean = np.mean(cluster_data)
        wcv += np.sum((cluster_data - cluster_mean) ** 2)
    
    # Between-cluster variance (BCV)
    bcv = 0.0
    for label in unique_labels:
        cluster_data = feature_values[labels == label]
        cluster_mean = np.mean(cluster_data)
        n_samples = len(cluster_data)
        bcv += n_samples * (cluster_mean - overall_mean) ** 2
    
    # Avoid division by zero
    if bcv == 0:
        return float('inf')
    
    return wcv / bcv


def _calculate_cv_normalized_metric(data: np.ndarray, labels: np.ndarray, k: int, 
                                     k_min: int, k_max: int, feature_col_idx: int = 0) -> float:
    """Calculate CV normalized metric (Option 2).
    
    Metric = (CV normalized over all clusters) × (# clusters normalized between k_min and k_max)
    
    Per traffic analysis literature:
    - k_min = 3
    - k_max = 2 × sqrt(n/2) where n is number of days
    
    Lower values indicate better clustering.
    
    Parameters:
    - data: Daily statistics array (n_days × n_features)
    - labels: Cluster labels for each day
    - k: Current number of clusters
    - k_min: Minimum cluster size (typically 3)
    - k_max: Maximum cluster size (typically 2 × sqrt(n/2))
    - feature_col_idx: Index of feature to use (0=avg_travel_time by default)
    
    Returns:
    - CV normalized metric
    """
    feature_values = data[:, feature_col_idx]
    unique_labels = np.unique(labels)
    
    # Calculate coefficient of variation for each cluster
    cvs = []
    for label in unique_labels:
        cluster_data = feature_values[labels == label]
        cluster_mean = np.mean(cluster_data)
        cluster_std = np.std(cluster_data, ddof=1) if len(cluster_data) > 1 else 0.0
        
        # CV = std / mean (avoid division by zero)
        if cluster_mean != 0:
            cv = cluster_std / abs(cluster_mean)
            cvs.append(cv)
    
    # Average CV across all clusters
    avg_cv = np.mean(cvs) if cvs else 0.0
    
    # Normalize CV (assuming typical range 0 to 1)
    cv_normalized = avg_cv
    
    # Normalize number of clusters between k_min and k_max
    if k_max > k_min:
        k_normalized = (k - k_min) / (k_max - k_min)
    else:
        k_normalized = 1.0
    
    # Combined metric
    return cv_normalized * k_normalized


def cluster_daily_patterns(
    cluster_csv: str,
    tmc_csv: Optional[str] = None,
    direction: Optional[str] = None,
    n_clusters: Optional[int] = None,
    travel_time_units: str = 'seconds',
    show_diagnostics: bool = False,
    stopping_criterion: str = 'silhouette',
    day_of_week: Optional[int] = None,
    start_hour: Optional[int] = None,
    end_hour: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster daily travel patterns using KMeans.
    
    First aggregates all TMC segments by direction to get corridor-level data:
    - SUMs travel times across all segments
    - AVERAGEs speeds across all segments
    Then clusters days based on average corridor travel time, peak travel time, 
    travel time variability, average speed, speed variability, and minimum speed.
    
    IMPORTANT: Clustering is performed separately for each direction.
    If direction is not specified, clusters both directions independently.
    
    Parameters:
    - cluster_csv: path to INRIX cluster travel-time CSV
    - tmc_csv: optional path to TMC identification CSV
    - direction: optional direction filter ('EB', 'WB', 'NB', 'SB', etc.)
                If None, processes all directions separately
    - n_clusters: number of clusters (if None, uses stopping criterion to auto-select)
    - travel_time_units: 'seconds' or 'minutes'
    - show_diagnostics: if True, shows diagnostic plots for all metrics
    - stopping_criterion: method for auto-selecting k ('silhouette', 'wcv_bcv', 'cv_normalized')
                         - 'silhouette': maximize silhouette score (general ML approach)
                         - 'wcv_bcv': minimize WCV/BCV ratio (traffic-specific, Option 1)
                         - 'cv_normalized': minimize CV × k_norm (traffic-specific, Option 2)
    - day_of_week: filter to specific day (0=Mon, 2=Wed, etc.). None = all days
    - start_hour: start hour (inclusive), 0-23. None = no filter
    - end_hour: end hour (exclusive), 0-24. None = no filter
    - start_date: start date 'YYYY-MM-DD'. None = no filter
    - end_date: end date 'YYYY-MM-DD'. None = no filter
    
    Returns:
    - Tuple of (daily_stats_with_clusters, corridor_data_with_clusters)
    """
    # Load raw TMC-level data
    df = _read_cluster_csv(cluster_csv)
    
    if travel_time_units.lower().startswith('s'):
        df['travel_time_min'] = df['travel_time'] / 60.0
    else:
        df['travel_time_min'] = df['travel_time']
    
    # Attach TMC metadata to get direction info
    if tmc_csv is not None:
        tdf = _read_tmc_csv(tmc_csv)
        df = _merge_with_tmc_dates(df, tdf)
    else:
        df['direction'] = 'ALL'
    
    # Filter by direction if specified
    if direction is not None:
        dir_map = {'EB': 'EASTBOUND', 'WB': 'WESTBOUND', 'NB': 'NORTHBOUND', 'SB': 'SOUTHBOUND'}
        search_dir = dir_map.get(direction.upper(), direction.upper())
        if 'direction' in df.columns:
            df = df[df['direction'].astype(str).str.upper().str.contains(search_dir)]
        else:
            print(f"Warning: No direction column found, processing all data")
    
    # Apply temporal filters if specified
    if any([day_of_week is not None, start_hour is not None, end_hour is not None, 
            start_date is not None, end_date is not None]):
        print(f"\nApplying temporal filters:")
        if day_of_week is not None:
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            print(f"  - Day of week: {day_names[day_of_week]}")
        if start_hour is not None or end_hour is not None:
            print(f"  - Time range: {start_hour or 0}:00 - {end_hour or 24}:00")
        if start_date is not None:
            print(f"  - Start date: {start_date}")
        if end_date is not None:
            print(f"  - End date: {end_date}")
        
        orig_len = len(df)
        df = filter_data(df, day_of_week=day_of_week, start_hour=start_hour, 
                        end_hour=end_hour, start_date=start_date, end_date=end_date)
        print(f"  - Records: {orig_len:,} → {len(df):,} ({100*len(df)/orig_len:.1f}%)")
    
    # STEP 1: Aggregate by timestamp + direction to get corridor-level data
    # This sums travel times and averages speeds across all TMC segments
    print("\nAggregating TMC segments to corridor level (sum travel times, mean speeds)...")
    corridor_data = df.groupby(['datetime', 'direction']).agg({
        'travel_time_min': 'sum',  # Sum all segment travel times
        'speed': 'mean' if 'speed' in df.columns else 'sum'  # Average speed across segments
    }).reset_index()
    
    corridor_data.columns = ['datetime', 'direction', 'travel_time_min', 'speed']
    
    # Add day column to corridor data
    corridor_data['day'] = corridor_data['datetime'].dt.date
    
    # If no direction specified, determine unique directions
    directions_to_process = [None]
    if direction is None and 'direction' in corridor_data.columns:
        directions_to_process = corridor_data['direction'].dropna().unique().tolist()
        if len(directions_to_process) > 1:
            print(f"\nProcessing {len(directions_to_process)} directions separately: {directions_to_process}")
    
    all_daily_stats = []
    all_corridor_with_clusters = []
    
    for dir_name in directions_to_process:
        # Filter corridor data for this direction
        if dir_name is not None:
            corridor_dir = corridor_data[corridor_data['direction'] == dir_name].copy()
            print(f"\n--- Clustering {dir_name} ---")
        else:
            corridor_dir = corridor_data.copy()
            dir_name = direction if direction else 'ALL'
        
        # STEP 2: Aggregate daily statistics from corridor-level data
        # Calculate meaningful daily statistics (NOT sum of all hourly values)
        daily_stats = corridor_dir.groupby('day').agg({
            'travel_time_min': ['mean', 'std', 'max'],  # Average, variability, and peak travel time
            'speed': ['mean', 'std', 'min']  # Average speed, variability, and minimum speed
        }).reset_index()
        
        # Flatten column names
        daily_stats.columns = ['day', 'avg_travel_time', 'travel_time_std', 'peak_travel_time', 
                              'avg_speed', 'speed_std', 'min_speed']
        
        feature_cols = ['avg_travel_time', 'travel_time_std', 'peak_travel_time', 'avg_speed', 'speed_std', 'min_speed']
    
        # Normalize features
        features = daily_stats[feature_cols]
        scaler = StandardScaler()
        normalized_features = scaler.fit_transform(features)
        
        # Determine optimal number of clusters if not provided
        n_clusters_to_use = n_clusters
        if n_clusters_to_use is None or show_diagnostics:
            # Calculate k_max using traffic-specific formula: 2 × sqrt(n/2)
            n_days = len(daily_stats)
            k_min = 3
            k_max = int(2 * np.sqrt(n_days / 2))
            k_range = range(k_min, min(k_max + 1, n_days // 2))
            
            inertias = []
            silhouette_scores_list = []
            wcv_bcv_ratios = []
            cv_normalized_metrics = []
            
            for k in k_range:
                kmeans_temp = KMeans(n_clusters=k, random_state=42, n_init=10)
                labels_temp = kmeans_temp.fit_predict(normalized_features)
                
                # Traditional ML metrics
                inertias.append(kmeans_temp.inertia_)
                silhouette_scores_list.append(silhouette_score(normalized_features, labels_temp))
                
                # Traffic-specific metrics (using avg_travel_time as primary feature - index 0)
                wcv_bcv = _calculate_wcv_bcv_ratio(features.values, labels_temp, feature_col_idx=0)
                wcv_bcv_ratios.append(wcv_bcv)
                
                cv_norm = _calculate_cv_normalized_metric(features.values, labels_temp, k, k_min, k_max, feature_col_idx=0)
                cv_normalized_metrics.append(cv_norm)
            
            if show_diagnostics:
                fig, axes = plt.subplots(2, 2, figsize=(14, 10))
                fig.suptitle(f'Cluster Analysis for {dir_name} (n={n_days} days, k_max={k_max})', 
                           fontsize=14, fontweight='bold')
                
                # Elbow plot
                axes[0, 0].plot(k_range, inertias, marker='o', linestyle='-', color='blue')
                axes[0, 0].set_xlabel('Number of Clusters (k)')
                axes[0, 0].set_ylabel('Inertia (Sum of Squared Distances)')
                axes[0, 0].set_title('Elbow Method for Optimal k')
                axes[0, 0].grid(True, alpha=0.3)
                
                # Silhouette plot
                axes[0, 1].plot(k_range, silhouette_scores_list, marker='o', linestyle='-', color='green')
                axes[0, 1].set_xlabel('Number of Clusters (k)')
                axes[0, 1].set_ylabel('Silhouette Score')
                axes[0, 1].set_title('Silhouette Score (higher is better)')
                axes[0, 1].grid(True, alpha=0.3)
                best_silhouette_k = list(k_range)[np.argmax(silhouette_scores_list)]
                axes[0, 1].axvline(best_silhouette_k, color='green', linestyle='--', alpha=0.5)
                
                # WCV/BCV ratio plot
                axes[1, 0].plot(k_range, wcv_bcv_ratios, marker='o', linestyle='-', color='red')
                axes[1, 0].set_xlabel('Number of Clusters (k)')
                axes[1, 0].set_ylabel('WCV / BCV Ratio')
                axes[1, 0].set_title('WCV/BCV Ratio (lower is better) - Option 1')
                axes[1, 0].grid(True, alpha=0.3)
                best_wcv_bcv_k = list(k_range)[np.argmin(wcv_bcv_ratios)]
                axes[1, 0].axvline(best_wcv_bcv_k, color='red', linestyle='--', alpha=0.5)
                
                # CV normalized metric plot
                axes[1, 1].plot(k_range, cv_normalized_metrics, marker='o', linestyle='-', color='purple')
                axes[1, 1].set_xlabel('Number of Clusters (k)')
                axes[1, 1].set_ylabel('CV × k_norm')
                axes[1, 1].set_title('CV Normalized Metric (lower is better) - Option 2')
                axes[1, 1].grid(True, alpha=0.3)
                best_cv_norm_k = list(k_range)[np.argmin(cv_normalized_metrics)]
                axes[1, 1].axvline(best_cv_norm_k, color='purple', linestyle='--', alpha=0.5)
                
                plt.tight_layout()
                plt.show()
                plt.close()
            
            if n_clusters_to_use is None:
                # Select optimal k based on stopping criterion
                if stopping_criterion.lower() == 'wcv_bcv':
                    best_k = list(k_range)[np.argmin(wcv_bcv_ratios)]
                    print(f"Suggested optimal clusters for {dir_name}: {best_k} (based on WCV/BCV ratio)")
                elif stopping_criterion.lower() == 'cv_normalized':
                    best_k = list(k_range)[np.argmin(cv_normalized_metrics)]
                    print(f"Suggested optimal clusters for {dir_name}: {best_k} (based on CV normalized metric)")
                else:  # default: silhouette
                    best_k = list(k_range)[np.argmax(silhouette_scores_list)]
                    print(f"Suggested optimal clusters for {dir_name}: {best_k} (based on silhouette score)")
                
                n_clusters_to_use = best_k
        
        # Perform clustering with chosen number of clusters
        kmeans = KMeans(n_clusters=n_clusters_to_use, random_state=42, n_init=10)
        daily_stats['cluster_label'] = kmeans.fit_predict(normalized_features)
        daily_stats['direction'] = dir_name
        
        # Print cluster distribution
        cluster_counts = daily_stats['cluster_label'].value_counts().sort_index()
        print(f"\nCluster distribution for {dir_name}:")
        for cluster_id, count in cluster_counts.items():
            pct = (count / len(daily_stats)) * 100
            print(f"  Cluster {int(cluster_id) + 1}: {count:3d} days ({pct:5.1f}%)")
        
        # Merge cluster labels back to corridor data
        corridor_dir = corridor_dir.merge(daily_stats[['day', 'cluster_label']], on='day', how='left')
        corridor_dir['direction'] = dir_name
        
        all_daily_stats.append(daily_stats)
        all_corridor_with_clusters.append(corridor_dir)
    
    # Combine results from all directions
    combined_daily_stats = pd.concat(all_daily_stats, ignore_index=True)
    combined_corridor = pd.concat(all_corridor_with_clusters, ignore_index=True)
    
    return combined_daily_stats, combined_corridor


def plot_cluster_distribution(daily_stats: pd.DataFrame, corridor_data: pd.DataFrame):
    """Plot time-series scatter colored by cluster labels.
    
    Shows how corridor travel time varies by time of day, colored by which
    cluster each day belongs to. Creates separate plots for each direction.
    X-axis is time of day (0-24 hours), all days overlaid.
    """
    # Check if we have multiple directions
    directions = corridor_data['direction'].unique() if 'direction' in corridor_data.columns else [None]
    
    for dir_name in directions:
        if dir_name is not None:
            corridor_dir = corridor_data[corridor_data['direction'] == dir_name]
            daily_dir = daily_stats[daily_stats['direction'] == dir_name]
            title_suffix = f' - {dir_name}'
        else:
            corridor_dir = corridor_data
            daily_dir = daily_stats
            title_suffix = ''
        
        fig, ax = plt.subplots(figsize=(14, 7))
        plt.style.use('ggplot')
        
        n_clusters = daily_dir['cluster_label'].nunique()
        color_map = plt.get_cmap('tab10', n_clusters)  # Use distinct colors
        
        for label in range(n_clusters):
            cluster_data = corridor_dir[corridor_dir['cluster_label'] == label]
            cluster_count = len(daily_dir[daily_dir['cluster_label'] == label])
            time_of_day = cluster_data['datetime'].dt.hour + cluster_data['datetime'].dt.minute / 60.0
            ax.scatter(time_of_day, cluster_data['travel_time_min'], 
                      color=color_map(label), alpha=0.1, s=20, 
                      label=f'Cluster {int(label) + 1} ({cluster_count} days)')
        
        ax.set_xlabel('Time of Day (hours)', fontsize=12)
        ax.set_ylabel('Corridor Travel Time (minutes)', fontsize=12)
        ax.set_title(f'Clusters of Daily Travel Patterns{title_suffix}', fontsize=14, fontweight='bold')
        ax.set_xlim(0, 24)
        ax.legend(title='Cluster Group', loc='upper right', framealpha=0.9)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()
        plt.close()


def plot_cluster_statistics(daily_stats: pd.DataFrame):
    """Plot summary statistics for each cluster. Creates separate plots for each direction."""
    # Check if we have multiple directions
    directions = daily_stats['direction'].unique() if 'direction' in daily_stats.columns else [None]
    
    for dir_name in directions:
        if dir_name is not None:
            daily_dir = daily_stats[daily_stats['direction'] == dir_name]
            title_suffix = f' - {dir_name}'
        else:
            daily_dir = daily_stats
            title_suffix = ''
        
        n_clusters = daily_dir['cluster_label'].nunique()
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle(f'Cluster Statistics{title_suffix}', fontsize=14, fontweight='bold')
        
        for label in range(n_clusters):
            cluster_data = daily_dir[daily_dir['cluster_label'] == label]
            color = plt.get_cmap('tab10')(label)
            n_days = len(cluster_data)
            
            axes[0, 0].boxplot([cluster_data['avg_travel_time']], positions=[label], 
                               widths=0.6, patch_artist=True,
                               boxprops=dict(facecolor=color, alpha=0.7),
                               tick_labels=[f'C{label+1}\n({n_days})'])
            axes[0, 1].boxplot([cluster_data['travel_time_std']], positions=[label],
                               widths=0.6, patch_artist=True,
                               boxprops=dict(facecolor=color, alpha=0.7),
                               tick_labels=[f'C{label+1}\n({n_days})'])
            axes[0, 2].boxplot([cluster_data['peak_travel_time']], positions=[label],
                               widths=0.6, patch_artist=True,
                               boxprops=dict(facecolor=color, alpha=0.7),
                               tick_labels=[f'C{label+1}\n({n_days})'])
            axes[1, 0].boxplot([cluster_data['avg_speed']], positions=[label],
                               widths=0.6, patch_artist=True,
                               boxprops=dict(facecolor=color, alpha=0.7),
                               tick_labels=[f'C{label+1}\n({n_days})'])
            if 'speed_std' in cluster_data.columns:
                axes[1, 1].boxplot([cluster_data['speed_std']], positions=[label],
                                   widths=0.6, patch_artist=True,
                                   boxprops=dict(facecolor=color, alpha=0.7),
                                   tick_labels=[f'C{label+1}\n({n_days})'])
            if 'min_speed' in cluster_data.columns:
                axes[1, 2].boxplot([cluster_data['min_speed']], positions=[label],
                                   widths=0.6, patch_artist=True,
                                   boxprops=dict(facecolor=color, alpha=0.7),
                                   tick_labels=[f'C{label+1}\n({n_days})'])
        
        axes[0, 0].set_title('Average Travel Time by Cluster')
        axes[0, 0].set_xlabel('Cluster (# days)')
        axes[0, 0].set_ylabel('Average Travel Time (minutes)')
        
        axes[0, 1].set_title('Travel Time Std Dev by Cluster')
        axes[0, 1].set_xlabel('Cluster (# days)')
        axes[0, 1].set_ylabel('Std Dev (minutes)')
        
        axes[0, 2].set_title('Peak Travel Time by Cluster')
        axes[0, 2].set_xlabel('Cluster (# days)')
        axes[0, 2].set_ylabel('Peak Travel Time (minutes)')
        
        axes[1, 0].set_title('Average Speed by Cluster')
        axes[1, 0].set_xlabel('Cluster (# days)')
        axes[1, 0].set_ylabel('Speed (mph)')
        
        if 'speed_std' in daily_dir.columns:
            axes[1, 1].set_title('Speed Std Dev by Cluster')
            axes[1, 1].set_xlabel('Cluster (# days)')
            axes[1, 1].set_ylabel('Std Dev (mph)')
        else:
            axes[1, 1].axis('off')
            
        if 'min_speed' in daily_dir.columns:
            axes[1, 2].set_title('Minimum Speed by Cluster')
            axes[1, 2].set_xlabel('Cluster (# days)')
            axes[1, 2].set_ylabel('Min Speed (mph)')
        else:
            axes[1, 2].axis('off')
        
        plt.tight_layout()
        plt.show()
        plt.close()


def plot_year_boxplots(
    cluster_csv: str,
    tmc_csv: str = None,
    direction: str = None,
    day_of_week: Optional[int] = None,
    start_hour: Optional[int] = None,
    end_hour: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    travel_time_units: str = 'seconds'
) -> pd.DataFrame:
    """Create box plots comparing travel times and speeds across years.
    
    Filters data to specific day of week and time period, then creates
    box plots showing distributions by year.
    
    Parameters:
    - cluster_csv: path to INRIX cluster travel-time CSV
    - tmc_csv: path to TMC identification CSV
    - direction: optional direction filter
    - day_of_week: 0=Monday, 1=Tuesday, 2=Wednesday, etc. None=all days
    - start_hour: start of time period (inclusive). None=no filter
    - end_hour: end of time period (exclusive). None=no filter
    - start_date: start date 'YYYY-MM-DD'. None=no filter
    - end_date: end date 'YYYY-MM-DD'. None=no filter
    - travel_time_units: 'seconds' or 'minutes'
    
    Returns:
    - Filtered DataFrame with travel time and speed data
    """
    # Load raw TMC-level data
    df = _read_cluster_csv(cluster_csv)
    
    if travel_time_units.lower().startswith('s'):
        df['travel_time_min'] = df['travel_time'] / 60.0
    else:
        df['travel_time_min'] = df['travel_time']
    
    # Attach TMC metadata to get direction info
    if tmc_csv is not None:
        tdf = _read_tmc_csv(tmc_csv)
        df = _merge_with_tmc_dates(df, tdf)
    
    # Filter by direction if specified
    if direction is not None:
        df = df[df['direction'].str.contains(direction, case=False, na=False)]
    
    # STEP 1: Aggregate TMC segments to corridor level (sum travel times, mean speeds)
    corridor_data = df.groupby(['datetime', 'direction']).agg({
        'travel_time_min': 'sum',
        'speed': 'mean'
    }).reset_index()
    
    # Add temporal features
    corridor_data['year'] = corridor_data['datetime'].dt.year
    
    # Apply temporal filters using filter_data function
    print(f'\nApplying temporal filters...')
    orig_len = len(corridor_data)
    filtered_data = filter_data(corridor_data, day_of_week=day_of_week, 
                                start_hour=start_hour, end_hour=end_hour,
                                start_date=start_date, end_date=end_date)
    
    print(f'Total records: {orig_len:,} → {len(filtered_data):,}')
    print(f'Years in data: {sorted(filtered_data["year"].unique())}')
    
    # Build filter description for plot title
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    filter_parts = []
    if day_of_week is not None:
        filter_parts.append(f"{day_names[day_of_week]}s")
    if start_hour is not None or end_hour is not None:
        filter_parts.append(f"{start_hour or 0}:00-{end_hour or 24}:00")
    filter_desc = ' '.join(filter_parts) if filter_parts else 'All Data'
    
    # Get unique directions
    directions = filtered_data['direction'].unique() if 'direction' in filtered_data.columns else ['ALL']
    
    for dir_name in directions:
        if len(directions) > 1:
            dir_data = filtered_data[filtered_data['direction'] == dir_name]
            title_suffix = f' - {dir_name}'
        else:
            dir_data = filtered_data
            title_suffix = ''
        
        years = sorted(dir_data['year'].unique())
        
        # Create box plots
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle(f'Year Comparison - {filter_desc}{title_suffix}', 
                     fontsize=14, fontweight='bold')
        
        # Prepare data for box plots
        travel_time_by_year = [dir_data[dir_data['year'] == year]['travel_time_min'].values 
                               for year in years]
        speed_by_year = [dir_data[dir_data['year'] == year]['speed'].values 
                        for year in years]
        
        # Travel time box plot
        bp1 = axes[0].boxplot(travel_time_by_year, tick_labels=[str(y) for y in years], 
                             patch_artist=True, widths=0.6)
        for patch, year in zip(bp1['boxes'], years):
            color = plt.get_cmap('viridis')((year - min(years)) / (max(years) - min(years) + 1)) if len(years) > 1 else plt.get_cmap('viridis')(0.5)
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        
        axes[0].set_xlabel('Year', fontsize=12)
        axes[0].set_ylabel('Corridor Travel Time (minutes)', fontsize=12)
        axes[0].set_title('Travel Time Distribution by Year')
        axes[0].grid(True, alpha=0.3, axis='y')
        
        # Speed box plot
        bp2 = axes[1].boxplot(speed_by_year, tick_labels=[str(y) for y in years], 
                             patch_artist=True, widths=0.6)
        for patch, year in zip(bp2['boxes'], years):
            color = plt.get_cmap('viridis')((year - min(years)) / (max(years) - min(years) + 1)) if len(years) > 1 else plt.get_cmap('viridis')(0.5)
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        
        axes[1].set_xlabel('Year', fontsize=12)
        axes[1].set_ylabel('Average Speed (mph)', fontsize=12)
        axes[1].set_title('Speed Distribution by Year')
        axes[1].grid(True, alpha=0.3, axis='y')
        
        # Print summary statistics
        print(f'\n--- Summary Statistics for {dir_name} ---')
        for year in years:
            year_data = dir_data[dir_data['year'] == year]
            print(f'\nYear {year}:')
            print(f'  N observations: {len(year_data)}')
            print(f'  Travel Time - Mean: {year_data["travel_time_min"].mean():.2f} min, '
                  f'Median: {year_data["travel_time_min"].median():.2f} min, '
                  f'Std: {year_data["travel_time_min"].std():.2f} min')
            print(f'  Speed - Mean: {year_data["speed"].mean():.2f} mph, '
                  f'Median: {year_data["speed"].median():.2f} mph, '
                  f'Std: {year_data["speed"].std():.2f} mph')
        
        plt.tight_layout()
        plt.show()
        plt.close()
    
    return filtered_data


def plot_corridor_times(agg_df: pd.DataFrame, corridor: str):
    """Plot times for a single corridor. Shows figure then closes it.

    This function will not save the plot to disk.
    """
    if corridor not in agg_df.columns:
        raise KeyError(f'Corridor {corridor} not found in aggregated data')
    plt.figure(figsize=(10, 4))
    plt.plot(agg_df.index, agg_df[corridor], marker='o')
    plt.title(f'Corridor {corridor} travel time (min)')
    plt.ylabel('Minutes')
    plt.xlabel('Time')
    plt.tight_layout()
    plt.show()
    plt.close()


if __name__ == '__main__':
    # ============================================================
    # CONFIGURATION - Edit these settings to filter your data
    # ============================================================
    
    # Data files
    cluster = 'I70-ROD2-Cluster-Travel-Time.csv'
    tmc = 'TMC_Identification.csv'
    
    # FILTERING SETTINGS - All analyses will use filtered data
    FILTER_CONFIG = {
        'day_of_week': 2,       # 0=Monday, 1=Tuesday, 2=Wednesday, etc. None=all days
        'start_hour': 6,        # Start hour (inclusive), 0-23. None=no filter
        'end_hour': 10,         # End hour (exclusive), 0-24. None=no filter
        'start_date': '2022-01-01',     # Start date 'YYYY-MM-DD'. None=no filter
        'end_date': "2022-12-31"        # End date 'YYYY-MM-DD'. None=no filter
    }
    
    # Analysis settings
    N_CLUSTERS = None           # Number of clusters for KMeans. None=auto-detect
    STOPPING_CRITERION = 'wcv_bcv'  # Auto-selection method: 'silhouette', 'wcv_bcv', or 'cv_normalized'
    SHOW_DIAGNOSTICS = True     # Show diagnostic plots with all metrics
    RESAMPLE_INTERVAL = '15min' # Resampling interval: '15min', '1h', etc.
    
    # ============================================================
    
    # Display filter settings
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    filter_desc = []
    if FILTER_CONFIG['day_of_week'] is not None:
        filter_desc.append(f"{day_names[FILTER_CONFIG['day_of_week']]}s only")
    if FILTER_CONFIG['start_hour'] is not None or FILTER_CONFIG['end_hour'] is not None:
        filter_desc.append(f"{FILTER_CONFIG['start_hour'] or 0}:00-{FILTER_CONFIG['end_hour'] or 24}:00")
    if FILTER_CONFIG['start_date'] is not None:
        filter_desc.append(f"from {FILTER_CONFIG['start_date']}")
    if FILTER_CONFIG['end_date'] is not None:
        filter_desc.append(f"to {FILTER_CONFIG['end_date']}")
    
    filter_display = ', '.join(filter_desc) if filter_desc else 'No filters (all data)'

    if os.path.exists(cluster):
        print('=' * 60)
        print('INRIX DATA AGGREGATION AND CLUSTERING EXAMPLE')
        print(f'DATA FILTER: {filter_display}')
        print('=' * 60)
        
        try:
            # ===== PART 1: Basic Aggregation =====
            print('\n--- Part 1: Basic Aggregation ---')
            agg = aggregate_travel_times(cluster, tmc_csv=tmc, resample=RESAMPLE_INTERVAL)
            print(f'Aggregated shape: {agg.shape}')
            print(f'Columns: {agg.columns.tolist()}')
            print(f'\nFirst few rows:\n{agg.head()}')
            
            # Filter by direction example (Eastbound)
            print('\n--- Eastbound only ---')
            agg_eb = aggregate_travel_times(cluster, tmc_csv=tmc, direction='EB', resample=RESAMPLE_INTERVAL)
            print(f'EB Aggregated shape: {agg_eb.shape}')
            print(f'EB Columns: {agg_eb.columns.tolist()}')
            
            # ===== PART 2: Clustering Analysis (with filters) =====
            print('\n' + '=' * 60)
            print('PART 2: CLUSTERING ANALYSIS (ALL DIRECTIONS)')
            print(f'Using filtered data: {filter_display}')
            print(f'Stopping criterion: {STOPPING_CRITERION}')
            print('=' * 60)
            print('Analyzing daily patterns for all directions separately...')
            daily_stats, df_with_clusters = cluster_daily_patterns(
                cluster, 
                tmc_csv=tmc, 
                direction=None,  # Process all directions
                n_clusters=N_CLUSTERS,
                show_diagnostics=SHOW_DIAGNOSTICS,
                stopping_criterion=STOPPING_CRITERION,
                **FILTER_CONFIG  # Apply temporal filters
            )
            
            # ===== PART 3: Visualization =====
            print('\n--- Part 3: Visualizations ---')
            print('Showing cluster distribution plot...')
            plot_cluster_distribution(daily_stats, df_with_clusters)
            
            print('Showing cluster statistics...')
            plot_cluster_statistics(daily_stats)
            
            # ===== PART 4: Time-of-Day Visualization =====
            print('\n--- Part 4: Time-of-Day Patterns (colored by year) ---')
            print('Showing all days overlaid by time of day...')
            
            # Use the corridor data with clusters
            for dir_name in df_with_clusters['direction'].unique():
                corridor_dir = df_with_clusters[df_with_clusters['direction'] == dir_name]
                
                # Extract year and time of day
                corridor_dir['year'] = corridor_dir['datetime'].dt.year
                corridor_dir['time_of_day'] = corridor_dir['datetime'].dt.hour + corridor_dir['datetime'].dt.minute / 60.0
                
                # Create figure with 2 subplots
                fig, axes = plt.subplots(1, 2, figsize=(16, 6))
                fig.suptitle(f'{dir_name} - All Days by Time of Day', fontsize=14, fontweight='bold')
                
                # Get unique years and assign colors
                years = sorted(corridor_dir['year'].unique())
                color_map = plt.get_cmap('tab10', len(years))
                
                # Plot travel time
                for idx, year in enumerate(years):
                    year_data = corridor_dir[corridor_dir['year'] == year]
                    axes[0].scatter(year_data['time_of_day'], year_data['travel_time_min'],
                                  color=color_map(idx), alpha=0.3, s=15, label=str(year))
                
                axes[0].set_xlabel('Time of Day (hours)', fontsize=12)
                axes[0].set_ylabel('Corridor Travel Time (minutes)', fontsize=12)
                axes[0].set_title('Travel Time by Time of Day')
                axes[0].set_xlim(0, 24)
                axes[0].legend(title='Year', loc='upper right', framealpha=0.9)
                axes[0].grid(True, alpha=0.3)
                
                # Plot speed
                if 'speed' in corridor_dir.columns:
                    for idx, year in enumerate(years):
                        year_data = corridor_dir[corridor_dir['year'] == year]
                        axes[1].scatter(year_data['time_of_day'], year_data['speed'],
                                      color=color_map(idx), alpha=0.3, s=15, label=str(year))
                    
                    axes[1].set_xlabel('Time of Day (hours)', fontsize=12)
                    axes[1].set_ylabel('Average Speed (mph)', fontsize=12)
                    axes[1].set_title('Speed by Time of Day')
                    axes[1].set_xlim(0, 24)
                    axes[1].legend(title='Year', loc='upper right', framealpha=0.9)
                    axes[1].grid(True, alpha=0.3)
                else:
                    axes[1].axis('off')
                
                plt.tight_layout()
                plt.show()
                plt.close()
            
            # ===== PART 5: Year Comparison (same filters as clustering) =====
            print('\n' + '=' * 60)
            print('PART 5: YEAR COMPARISON ANALYSIS')
            print(f'Using filtered data: {filter_display}')
            print('=' * 60)
            
            filtered_data = plot_year_boxplots(
                cluster, 
                tmc_csv=tmc,
                direction=None,  # Analyze all directions
                **FILTER_CONFIG  # Use same filters as clustering
            )
            
            print('\n' + '=' * 60)
            print('Analysis complete!')
            print('=' * 60)
                
        except Exception as e:
            print(f'Example run failed: {e}')
            import traceback
            traceback.print_exc()
    else:
        print('Example data not found in current directory.')
        print(f'Looking for: {os.path.abspath(cluster)}')
