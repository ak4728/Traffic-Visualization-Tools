
# Traffic Visualization Tools

## Overview
A comprehensive suite of interactive web-based visualization tools for traffic engineering analysis, transportation planning, and simulation modeling. These tools provide real-time interactive visualizations for various traffic scenarios including signal timing optimization, origin-destination analysis, travel time patterns, and conference seating dynamics.

## Tools Included

### 🚦 Traffic Signal Release Function Visualizer (`index.html` & `SigRelease.html`)
Interactive visualization tool for analyzing traffic signal release patterns and timing optimization. Features real-time parameter adjustment and multiple visualization modes.

**Key Features:**
- Real-time signal timing parameter adjustment
- Multiple release function models
- Interactive charts and graphs
- Export functionality for analysis results

### 🗺️ Interactive Origin-Destination Matrix Visualization (`SantaFeOD.html`)
Advanced geospatial visualization tool for analyzing traffic flow patterns using origin-destination matrices with integrated mapping capabilities.

**Key Features:**
- Interactive map interface using Leaflet.js
- Arc-based flow visualization between origins and destinations
- Real-time data filtering and selection
- Dynamic flow animation and styling controls
- Geographic context for traffic pattern analysis

### 📊 PENA BLVD Travel Time Visualization (`PenaViz.html`)
Specialized tool for analyzing travel time patterns on PENA Boulevard with advanced charting capabilities and time-series analysis.

**Key Features:**
- Multi-chart dashboard with Chart.js integration
- Time-series travel time analysis
- Comparative analysis tools
- Dark theme optimized for extended viewing
- Statistical summaries and trend analysis

### 🎤 Conference Seating Simulation (`confSeating.html`)
Agent-based simulation for modeling conference seating dynamics and crowd behavior patterns.

**Key Features:**
- Real-time agent-based simulation
- Configurable attendee parameters
- Speed and density controls
- Visual feedback and statistics
- Behavioral pattern analysis

## Quick Start

1. **Download/Clone the Repository**
   ```bash
   git clone [repository-url]
   cd Traffic-Visualization-Tools
   ```

2. **Open Tools**
   - Simply open any `.html` file in a modern web browser
   - No server setup required for basic functionality
   - For full functionality with external data, use a local server

3. **Load Data**
   - Use the built-in data loading interfaces
   - Supported formats: JSON, CSV
   - Sample data files included: `travel_data.json`, `penaviz_data.json`

## Data Format Requirements

### Origin-Destination Data (SantaFeOD.html)
```json
{
  "zones": [
    {"id": "zone1", "lat": 35.6870, "lon": -105.9378, "name": "Zone Name"}
  ],
  "flows": [
    {"origin": "zone1", "destination": "zone2", "volume": 150}
  ]
}
```

### Travel Time Data (PenaViz.html)
```json
{
  "timepoints": ["06:00", "06:15", "06:30"],
  "travel_times": [12.5, 14.2, 16.8]
}
```

## Dependencies

### External Libraries
- **Leaflet.js** (v1.9.4) - Interactive mapping for SantaFeOD visualization
- **Leaflet-Arc** - Arc drawing extensions for flow visualization  
- **Chart.js** (v4.4.0) - Advanced charting for travel time analysis
- **Modern Web Browser** - Chrome, Firefox, Safari, or Edge with ES6 support

### Built-in Components
- Custom CSS styling (`styles.css`)
- JavaScript simulation engine (`simulation.js`)
- Debug utilities (`debug_restart.js`)

## Browser Compatibility
- Chrome 80+
- Firefox 75+
- Safari 13+
- Edge 80+

## File Structure
```
Traffic-Visualization-Tools/
├── index.html              # Main traffic signal visualizer
├── SigRelease.html          # Signal release function analysis
├── SantaFeOD.html          # Origin-destination matrix visualization
├── PenaViz.html            # PENA Boulevard travel time analysis
├── confSeating.html        # Conference seating simulation
├── styles.css              # Shared styling
├── simulation.js           # Simulation engine
├── debug_restart.js        # Debug utilities
├── travel_data.json        # Sample travel time data
├── penaviz_data.json       # Sample visualization data
└── README.md              # This file
```

## Usage Examples

### Signal Timing Analysis
1. Open `index.html` or `SigRelease.html`
2. Adjust signal timing parameters using the control panel
3. Observe real-time visualization updates
4. Export results for further analysis

### Traffic Flow Analysis
1. Open `SantaFeOD.html`
2. Load your origin-destination data
3. Use map controls to explore flow patterns
4. Adjust visualization settings for optimal viewing

### Travel Time Monitoring
1. Open `PenaViz.html`
2. Load travel time data
3. Analyze patterns using multiple chart views
4. Export visualizations and statistics

## Contributing
We welcome contributions! Please follow these guidelines:
- Fork the repository
- Create feature branches for new tools or enhancements
- Test all changes across multiple browsers
- Submit pull requests with detailed descriptions
- Follow existing code style and structure

## License
Licensed under the GPL-3.0 License. See [LICENSE](LICENSE) file for details.

## Support
For questions, bug reports, or feature requests, please open an issue on the project repository.

---
*Last updated: January 2026*
