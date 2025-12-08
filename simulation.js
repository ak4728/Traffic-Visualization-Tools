// ===== CONFERENCE SEATING SIMULATION ===== //

// ===== CONSTANTS & CONFIGURATION ===== //

// Grid cell types
const CELL_TYPES = {
    EMPTY: 0,
    SEAT: 1,
    CORRIDOR: 2,
    GATE: 3,
    SEATED_AGENT: 9,
    STANDING: 8
};

// Visual constants
const VISUAL_CONFIG = {
    CELL_SIZE: 10,
    COLORS: {
        [CELL_TYPES.EMPTY]: '#ffffff',
        [CELL_TYPES.SEAT]: '#ffeb3b',
        [CELL_TYPES.CORRIDOR]: '#add8e6',
        [CELL_TYPES.GATE]: '#00ff00',
        [CELL_TYPES.STANDING]: '#666666',
        [CELL_TYPES.SEATED_AGENT]: '#ff0000'
    },
    BLOCK_COLORS: ['#2196f3', '#ff9800', '#9c27b0', '#00bcd4', '#e91e63', '#8bc34a']
};

// Simulation constants
const SIM_CONSTANTS = {
    SEAT_ROWS: { START: 6, END: 14 },
    BACK_ROWS: { START: 14, END: 19 },
    GATE_POSITIONS: [10, 34, 58],
    PATH_ROW_RANGE: { START: 16, END: 19 },
    DEFAULT_ROW_THRESHOLD: 5
};

// ===== CONFIGURATION MANAGER ===== //

class ConfigManager {
    constructor() {
        this.config = {
            ROWS: 20,
            COLS: 68,
            NUM_BLOCKS: 4,
            CORRIDOR_WIDTH: 4,
            FEATURE_ASSIGNED_SEATS: true,
            FEATURE_COLOR_BY_BLOCK: true,
            NUM_AGENTS: 384,
            SPEED: 100,
            MAX_TIME: 500,
            SOCIAL_DISTANCE: 8,
            BACK_PREF: 3
        };
        this.listeners = new Set();
    }

    set(key, value) {
        if (this.validate(key, value)) {
            this.config[key] = value;
            this.notifyListeners(key, value);
        }
    }

    get(key) {
        return this.config[key];
    }

    validate(key, value) {
        const validations = {
            NUM_AGENTS: v => v >= 50 && v <= 500,
            SPEED: v => v >= 10 && v <= 500,
            MAX_TIME: v => v >= 200 && v <= 1000,
            NUM_BLOCKS: v => v >= 2 && v <= 6,
            CORRIDOR_WIDTH: v => v >= 2 && v <= 6,
            SOCIAL_DISTANCE: v => v >= 0 && v <= 15,
            BACK_PREF: v => v >= 0 && v <= 10
        };

        const validator = validations[key];
        return !validator || validator(value);
    }

    addListener(callback) {
        this.listeners.add(callback);
    }

    removeListener(callback) {
        this.listeners.delete(callback);
    }

    notifyListeners(key, value) {
        this.listeners.forEach(callback => {
            try {
                callback(key, value);
            } catch (error) {
                console.error('Config listener error:', error);
            }
        });
    }
}

// ===== UTILITY FUNCTIONS ===== //

class Utils {
    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    static weightedChoice(items, weights) {
        try {
            const total = weights.reduce((a, b) => a + b, 0);
            if (total === 0) return items[0];
            
            let rnd = Math.random() * total;
            for (let i = 0; i < items.length; i++) {
                rnd -= weights[i];
                if (rnd <= 0) return items[i];
            }
            return items[items.length - 1];
        } catch (error) {
            console.error('Weighted choice error:', error);
            return items[0] || null;
        }
    }

    static clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    static isValidPosition(row, col, maxRow, maxCol) {
        return row >= 0 && row < maxRow && col >= 0 && col < maxCol;
    }
}

// ===== GRID BUILDER ===== //

class GridBuilder {
    static generateSeatBlocks(cols, numBlocks, corridorWidth) {
        const totalSeat = cols - (numBlocks + 1) * corridorWidth;
        const blockWidth = Math.floor(totalSeat / numBlocks);
        const blocks = {};
        
        for (let i = 0; i < numBlocks; i++) {
            const start = corridorWidth + i * (blockWidth + corridorWidth);
            blocks[i] = [start, start + blockWidth - 1];
        }
        return blocks;
    }

    static generateCorridorSegments(cols, seatBlocks, corridorWidth) {
        const segments = [];
        const leftMargin = Array.from({length: corridorWidth}, (_, i) => i);
        segments.push(leftMargin);
        
        for (let i = 0; i < Object.keys(seatBlocks).length; i++) {
            const end = seatBlocks[i][1];
            const seg = Array.from({length: corridorWidth}, (_, j) => end + 1 + j);
            segments.push(seg);
        }
        return segments;
    }

    static buildGrid(config) {
        try {
            const grid = Array(config.ROWS).fill(null).map(() => Array(config.COLS).fill(CELL_TYPES.EMPTY));
            
            const seatBlocks = this.generateSeatBlocks(config.COLS, config.NUM_BLOCKS, config.CORRIDOR_WIDTH);
            const corridorSegs = this.generateCorridorSegments(config.COLS, seatBlocks, config.CORRIDOR_WIDTH);
            
            // Fill seats
            for (let r = SIM_CONSTANTS.SEAT_ROWS.START; r < SIM_CONSTANTS.SEAT_ROWS.END; r++) {
                for (let block in seatBlocks) {
                    const [c0, c1] = seatBlocks[block];
                    for (let c = c0; c <= c1; c++) {
                        grid[r][c] = CELL_TYPES.SEAT;
                    }
                }
            }
            
            // Fill corridors
            for (let r = 0; r < config.ROWS; r++) {
                corridorSegs.forEach(seg => {
                    seg.forEach(c => {
                        if (grid[r][c] === CELL_TYPES.EMPTY) {
                            grid[r][c] = CELL_TYPES.CORRIDOR;
                        }
                    });
                });
            }
            
            // Add gates
            const gates = SIM_CONSTANTS.GATE_POSITIONS.filter(c => c < config.COLS);
            gates.forEach(c => {
                grid[config.ROWS - 1][c] = CELL_TYPES.GATE;
            });
            
            return grid;
        } catch (error) {
            console.error('Grid building error:', error);
            return null;
        }
    }
}

// ===== PATHFINDING & SEAT SELECTION ===== //

class PathfindingEngine {
    static computeSimplePath(spawn, corridor, seat, row0) {
        const path = [];
        let [r, c] = spawn;
        const [r1, c1] = seat;
        
        try {
            if (r !== row0) {
                const step = r > row0 ? -1 : 1;
                for (let rr = r + step; rr !== row0 + step; rr += step) {
                    path.push([rr, c]);
                }
            }
            
            if (c !== corridor) {
                const step = corridor > c ? 1 : -1;
                for (let cc = c + step; cc !== corridor + step; cc += step) {
                    path.push([row0, cc]);
                }
            }
            
            if (row0 > r1) {
                for (let rr = row0 - 1; rr >= r1; rr--) {
                    path.push([rr, corridor]);
                }
            }
            
            if (corridor !== c1) {
                const step = c1 > corridor ? 1 : -1;
                for (let cc = corridor + step; cc !== c1 + step; cc += step) {
                    path.push([r1, cc]);
                }
            }
            
            return path;
        } catch (error) {
            console.error('Path computation error:', error);
            return [];
        }
    }

    static pickBlockBasedOnGate(gateCol) {
        if (gateCol <= 10) {
            return Utils.weightedChoice([0, 1], [0.75, 0.25]);
        } else if (gateCol <= 34) {
            return Utils.weightedChoice([1, 2], [0.25, 0.75]);
        } else {
            return Utils.weightedChoice([2, 3], [0.25, 0.75]);
        }
    }

    static pickPreferredCorridorCell(block, seatCol, blockToCorridorCells) {
        const segments = blockToCorridorCells[block];
        if (!segments) return 4; // fallback
        
        try {
            const segWeights = segments.map(seg => {
                const d = Math.min(...seg.map(c => Math.abs(seatCol - c)));
                return 1.0 / (d + 1);
            });
            
            const chosenSeg = Utils.weightedChoice(segments, segWeights);
            return chosenSeg.reduce((best, c) => 
                Math.abs(seatCol - c) < Math.abs(seatCol - best) ? c : best
            );
        } catch (error) {
            console.error('Corridor cell selection error:', error);
            return segments[0] ? segments[0][0] : 4;
        }
    }
}

// ===== SEAT SELECTION ENGINE ===== //

class SeatSelectionEngine {
    static rowOccupancy(grid, row, c0, c1) {
        let count = 0;
        for (let c = c0; c <= c1; c++) {
            if (grid[row][c] === CELL_TYPES.SEATED_AGENT || grid[row][c] === CELL_TYPES.STANDING) {
                count++;
            }
        }
        return count;
    }

    static countAdjacentSeated(grid, seat) {
        const [r, c] = seat;
        let count = 0;
        const dirs = [[-1,0], [1,0], [0,-1], [0,1], [-1,-1], [-1,1], [1,-1], [1,1]];
        
        for (const [dr, dc] of dirs) {
            const rr = r + dr, cc = c + dc;
            if (Utils.isValidPosition(rr, cc, grid.length, grid[0].length)) {
                if (grid[rr][cc] === CELL_TYPES.SEATED_AGENT) count++;
            }
        }
        return count;
    }

    static pickSeatInBlock(grid, block, assigned, seatBlocks, config, rowThr = SIM_CONSTANTS.DEFAULT_ROW_THRESHOLD) {
        try {
            const [c0, c1] = seatBlocks[block];
            const valid = [];
            
            for (let r = SIM_CONSTANTS.SEAT_ROWS.START; r < SIM_CONSTANTS.SEAT_ROWS.END; r++) {
                if (this.rowOccupancy(grid, r, c0, c1) >= rowThr) continue;
                
                for (let c = c0; c <= c1; c++) {
                    const key = `${r},${c}`;
                    if (grid[r][c] === CELL_TYPES.SEAT && !assigned.has(key)) {
                        let w = 0;
                        
                        // Back row preference (higher row numbers = further back)
                        const backRowWeight = (r - SIM_CONSTANTS.SEAT_ROWS.START) * config.BACK_PREF;
                        w += backRowWeight;
                        
                        // Aisle preference
                        const aisleWeight = Math.min(c - c0, c1 - c) <= 1 ? 5 : 0;
                        w += aisleWeight;
                        
                        // Social distance preference (fewer neighbors = higher weight)
                        // If adjacentCount = 0 (no neighbors), weight += 8 * socialDistance
                        // If adjacentCount = 8 (max neighbors), weight += 0 * socialDistance
                        const adjacentCount = this.countAdjacentSeated(grid, [r, c]);
                        const socialWeight = (8 - adjacentCount) * config.SOCIAL_DISTANCE;
                        w += socialWeight;
                        
                        // Optional: Log seat selection details for debugging
                        if (Math.random() < 0.01) { // Log 1% of seat evaluations
                            console.log(`Seat [${r},${c}]: back=${backRowWeight}, aisle=${aisleWeight}, social=${socialWeight}, total=${w}`);
                        }
                        
                        valid.push([[r, c], Math.max(w, 1)]);
                    }
                }
            }
            
            if (valid.length === 0) return null;
            const seats = valid.map(v => v[0]);
            const weights = valid.map(v => v[1]);
            return Utils.weightedChoice(seats, weights);
        } catch (error) {
            console.error('Seat selection error:', error);
            return null;
        }
    }

    static pickSeatAnyBlock(grid, assigned, seatBlocks, config, rowThr = SIM_CONSTANTS.DEFAULT_ROW_THRESHOLD) {
        const blocks = Object.keys(seatBlocks).map(Number);
        const shuffled = blocks.sort(() => Math.random() - 0.5);
        
        for (const b of shuffled) {
            const s = this.pickSeatInBlock(grid, b, assigned, seatBlocks, config, rowThr);
            if (s) return [b, s];
        }
        return [null, null];
    }

    static findStandingPosition(grid) {
        try {
            // Try to find standing positions in the back rows
            for (const r of [19, 18, 17, 16, 15, 14]) {
                const candidates = [];
                
                for (let c = 0; c < grid[0].length; c++) {
                    const cellType = grid[r][c];
                    if (cellType !== CELL_TYPES.SEAT && 
                        cellType !== CELL_TYPES.GATE && 
                        cellType !== CELL_TYPES.SEATED_AGENT && 
                        cellType !== CELL_TYPES.STANDING) {
                        candidates.push([r, c]);
                    }
                }
                
                if (candidates.length > 0) {
                    return candidates[Math.floor(Math.random() * candidates.length)];
                }
            }
            
            // Fallback
            const r = SIM_CONSTANTS.BACK_ROWS.START + Math.floor(Math.random() * 6);
            const c = Math.floor(Math.random() * grid[0].length);
            return [r, c];
        } catch (error) {
            console.error('Standing position selection error:', error);
            return [18, 10]; // Safe fallback
        }
    }
}

// ===== AGENT CLASS ===== //

class Agent {
    constructor(grid, spawn, assigned, seatBlocks, blockToCorridorCells, config) {
        try {
            this.pos = spawn;
            this.seated = false;
            this.standing = false;
            this.willStand = false;
            
            const gateC = spawn[1];
            this.block = PathfindingEngine.pickBlockBasedOnGate(gateC);
            
            if (this.block >= Object.keys(seatBlocks).length) {
                this.block = Object.keys(seatBlocks).length - 1;
            }
            
            let seat = SeatSelectionEngine.pickSeatInBlock(grid, this.block, assigned, seatBlocks, config);
            if (!seat) {
                const [b, s] = SeatSelectionEngine.pickSeatAnyBlock(grid, assigned, seatBlocks, config);
                if (!s) {
                    // No seats available - will stand in back
                    const standPos = SeatSelectionEngine.findStandingPosition(grid);
                    this.seat = standPos;
                    this.corridor = config.CORRIDOR_WIDTH;
                    this.row0 = 19;
                    this.path = PathfindingEngine.computeSimplePath(this.pos, this.corridor, this.seat, this.row0);
                    this.willStand = true;
                    return;
                }
                this.block = b;
                seat = s;
            }
            
            if (config.FEATURE_ASSIGNED_SEATS) {
                assigned.add(`${seat[0]},${seat[1]}`);
            }
            
            this.seat = seat;
            this.corridor = PathfindingEngine.pickPreferredCorridorCell(this.block, this.seat[1], blockToCorridorCells);
            this.row0 = SIM_CONSTANTS.PATH_ROW_RANGE.START + Math.floor(Math.random() * 4);
            this.path = PathfindingEngine.computeSimplePath(this.pos, this.corridor, this.seat, this.row0);
        } catch (error) {
            console.error('Agent creation error:', error);
            // Set safe defaults
            this.pos = spawn;
            this.seated = false;
            this.standing = true;
            this.path = [];
        }
    }
    
    update(grid) {
        if (this.seated || this.standing) return;
        
        try {
            if (this.path.length === 0) {
                // Reached destination
                if (this.willStand) {
                    this.standing = true;
                    grid[this.pos[0]][this.pos[1]] = CELL_TYPES.STANDING;
                } else if (grid[this.pos[0]][this.pos[1]] === CELL_TYPES.SEAT) {
                    this.seated = true;
                    grid[this.pos[0]][this.pos[1]] = CELL_TYPES.SEATED_AGENT;
                } else {
                    // Something went wrong, mark as standing
                    this.standing = true;
                    grid[this.pos[0]][this.pos[1]] = CELL_TYPES.STANDING;
                }
                return;
            }
            
            this.pos = this.path.shift();
        } catch (error) {
            console.error('Agent update error:', error);
            this.standing = true;
        }
    }
}

// ===== RENDERER CLASS ===== //

class Renderer {
    constructor(canvas, chartCanvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.chartCanvas = chartCanvas;
        this.chartCtx = chartCanvas.getContext('2d');
        
        this.setupCanvases();
    }

    setupCanvases() {
        try {
            // Set chart canvas to match container size with high DPI
            this.resizeChart();
            window.addEventListener('resize', () => this.resizeChart());
        } catch (error) {
            console.error('Canvas setup error:', error);
        }
    }

    resizeChart() {
        try {
            const container = this.chartCanvas.parentElement;
            const dpr = window.devicePixelRatio || 1;
            this.chartCanvas.width = container.clientWidth * dpr;
            this.chartCanvas.height = 400 * dpr;
            this.chartCanvas.style.width = container.clientWidth + 'px';
            this.chartCanvas.style.height = '400px';
            this.chartCtx.scale(dpr, dpr);
        } catch (error) {
            console.error('Chart resize error:', error);
        }
    }

    drawGrid(grid, agents, config) {
        try {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            
            // Draw grid cells
            for (let r = 0; r < config.ROWS; r++) {
                for (let c = 0; c < config.COLS; c++) {
                    const cellValue = grid[r][c];
                    this.ctx.fillStyle = VISUAL_CONFIG.COLORS[cellValue];
                    this.ctx.fillRect(c * VISUAL_CONFIG.CELL_SIZE, r * VISUAL_CONFIG.CELL_SIZE, 
                                    VISUAL_CONFIG.CELL_SIZE, VISUAL_CONFIG.CELL_SIZE);
                    
                    // Add borders for special cells
                    if (cellValue === CELL_TYPES.GATE) {
                        this.ctx.strokeStyle = '#000';
                        this.ctx.lineWidth = 2;
                        this.ctx.strokeRect(c * VISUAL_CONFIG.CELL_SIZE, r * VISUAL_CONFIG.CELL_SIZE, 
                                          VISUAL_CONFIG.CELL_SIZE, VISUAL_CONFIG.CELL_SIZE);
                    } else if (cellValue === CELL_TYPES.STANDING) {
                        this.ctx.strokeStyle = '#333';
                        this.ctx.lineWidth = 1;
                        this.ctx.strokeRect(c * VISUAL_CONFIG.CELL_SIZE, r * VISUAL_CONFIG.CELL_SIZE, 
                                          VISUAL_CONFIG.CELL_SIZE, VISUAL_CONFIG.CELL_SIZE);
                    } else {
                        this.ctx.strokeStyle = '#ddd';
                        this.ctx.lineWidth = 0.5;
                        this.ctx.strokeRect(c * VISUAL_CONFIG.CELL_SIZE, r * VISUAL_CONFIG.CELL_SIZE, 
                                          VISUAL_CONFIG.CELL_SIZE, VISUAL_CONFIG.CELL_SIZE);
                    }
                }
            }
            
            // Draw moving agents
            agents.forEach(agent => {
                if (!agent.seated && !agent.standing) {
                    const [r, c] = agent.pos;
                    if (agent.willStand) {
                        this.ctx.fillStyle = '#999'; // Gray for standing agents
                    } else {
                        this.ctx.fillStyle = config.FEATURE_COLOR_BY_BLOCK ? 
                            VISUAL_CONFIG.BLOCK_COLORS[agent.block % VISUAL_CONFIG.BLOCK_COLORS.length] : 'black';
                    }
                    this.ctx.beginPath();
                    this.ctx.arc(c * VISUAL_CONFIG.CELL_SIZE + VISUAL_CONFIG.CELL_SIZE / 2, 
                               r * VISUAL_CONFIG.CELL_SIZE + VISUAL_CONFIG.CELL_SIZE / 2, 
                               VISUAL_CONFIG.CELL_SIZE / 2.5, 0, Math.PI * 2);
                    this.ctx.fill();
                }
            });
        } catch (error) {
            console.error('Grid drawing error:', error);
        }
    }

    drawChart(chartData) {
        if (!chartData || chartData.time.length === 0) return;
        
        try {
            const container = this.chartCanvas.parentElement;
            const displayWidth = container.clientWidth;
            const displayHeight = 400;
            
            this.chartCtx.clearRect(0, 0, displayWidth, displayHeight);
            
            const padding = 50;
            const width = displayWidth - 2 * padding;
            const height = displayHeight - 2 * padding;
            
            const maxTime = Math.max(...chartData.time, 1);
            const maxValue = Math.max(...chartData.seated, ...chartData.standing, 1);
            
            // Draw background
            this.chartCtx.fillStyle = '#ffffff';
            this.chartCtx.fillRect(0, 0, displayWidth, displayHeight);
            
            // Draw grid lines
            this.chartCtx.strokeStyle = '#e0e0e0';
            this.chartCtx.lineWidth = 1;
            for (let i = 0; i <= 5; i++) {
                const y = padding + (i * height) / 5;
                this.chartCtx.beginPath();
                this.chartCtx.moveTo(padding, y);
                this.chartCtx.lineTo(padding + width, y);
                this.chartCtx.stroke();
            }
            
            // Draw axes
            this.chartCtx.strokeStyle = '#333';
            this.chartCtx.lineWidth = 2;
            this.chartCtx.beginPath();
            this.chartCtx.moveTo(padding, padding);
            this.chartCtx.lineTo(padding, padding + height);
            this.chartCtx.lineTo(padding + width, padding + height);
            this.chartCtx.stroke();
            
            // Draw data lines
            this.drawDataLine(chartData.seated, maxTime, maxValue, width, height, padding, '#ff0000');
            this.drawDataLine(chartData.standing, maxTime, maxValue, width, height, padding, '#666');
            
            // Draw labels and legend
            this.drawChartLabels(maxValue, maxTime, displayWidth, displayHeight, padding, width, height);
        } catch (error) {
            console.error('Chart drawing error:', error);
        }
    }

    drawDataLine(data, maxTime, maxValue, width, height, padding, color) {
        if (data.length <= 1) return;
        
        this.chartCtx.strokeStyle = color;
        this.chartCtx.lineWidth = 3;
        this.chartCtx.beginPath();
        
        for (let i = 0; i < data.length; i++) {
            const x = padding + (i / Math.max(data.length - 1, 1)) * width;
            const y = padding + height - (data[i] / maxValue) * height;
            
            if (i === 0) this.chartCtx.moveTo(x, y);
            else this.chartCtx.lineTo(x, y);
        }
        this.chartCtx.stroke();
    }

    drawChartLabels(maxValue, maxTime, displayWidth, displayHeight, padding, width, height) {
        // Y-axis labels
        this.chartCtx.fillStyle = '#333';
        this.chartCtx.font = '12px Arial';
        this.chartCtx.textAlign = 'right';
        for (let i = 0; i <= 5; i++) {
            const value = Math.round((maxValue / 5) * (5 - i));
            const y = padding + (i * height) / 5;
            this.chartCtx.fillText(value.toString(), padding - 10, y + 4);
        }
        
        // X-axis labels
        this.chartCtx.textAlign = 'center';
        for (let i = 0; i <= 5; i++) {
            const value = Math.round((maxTime / 5) * i);
            const x = padding + (i * width) / 5;
            this.chartCtx.fillText(value.toString(), x, padding + height + 20);
        }
        
        // Axis titles
        this.chartCtx.font = 'bold 14px Arial';
        this.chartCtx.fillText('Time (ticks)', displayWidth / 2, displayHeight - 10);
        
        this.chartCtx.save();
        this.chartCtx.translate(15, displayHeight / 2);
        this.chartCtx.rotate(-Math.PI / 2);
        this.chartCtx.fillText('Number of People', 0, 0);
        this.chartCtx.restore();
        
        // Legend
        this.chartCtx.textAlign = 'left';
        this.chartCtx.font = '12px Arial';
        
        this.chartCtx.fillStyle = '#ff0000';
        this.chartCtx.fillRect(displayWidth - 110, 20, 20, 3);
        this.chartCtx.fillStyle = '#333';
        this.chartCtx.fillText('Seated', displayWidth - 85, 25);
        
        this.chartCtx.fillStyle = '#666';
        this.chartCtx.fillRect(displayWidth - 110, 40, 20, 3);
        this.chartCtx.fillStyle = '#333';
        this.chartCtx.fillText('Standing', displayWidth - 85, 45);
    }
}

// ===== SIMULATION ENGINE ===== //

class SimulationEngine {
    constructor(config) {
        this.config = config;
        this.grid = null;
        this.agents = [];
        this.spawned = 0;
        this.time = 0;
        this.completed = false;
        this.assigned = new Set();
        this.gates = [];
        this.seatBlocks = {};
        this.corridorSegs = [];
        this.blockToCorridorCells = {};
        this.chartData = { time: [], seated: [], standing: [] };
    }

    initialize() {
        try {
            this.grid = GridBuilder.buildGrid(this.config);
            if (!this.grid) {
                throw new Error('Failed to build grid');
            }
            
            this.agents = [];
            this.spawned = 0;
            this.time = 0;
            this.completed = false;
            this.assigned = new Set();
            
            const gatePositions = SIM_CONSTANTS.GATE_POSITIONS.filter(c => c < this.config.COLS);
            this.gates = gatePositions.map(c => [this.config.ROWS - 1, c]);
            
            this.seatBlocks = GridBuilder.generateSeatBlocks(this.config.COLS, this.config.NUM_BLOCKS, this.config.CORRIDOR_WIDTH);
            this.corridorSegs = GridBuilder.generateCorridorSegments(this.config.COLS, this.seatBlocks, this.config.CORRIDOR_WIDTH);
            
            this.blockToCorridorCells = {};
            for (let i = 0; i < this.config.NUM_BLOCKS; i++) {
                this.blockToCorridorCells[i] = [this.corridorSegs[i], this.corridorSegs[i + 1]];
            }
            
            this.chartData = { time: [], seated: [], standing: [] };
            return true;
        } catch (error) {
            console.error('Simulation initialization error:', error);
            return false;
        }
    }

    update() {
        if (this.completed) return;
        
        try {
            // Track occupied positions
            const occupied = new Set();
            this.agents.forEach(agent => {
                if (!agent.seated && !agent.standing) {
                    occupied.add(`${agent.pos[0]},${agent.pos[1]}`);
                }
            });
            
            // Spawn new agents
            for (const gate of this.gates) {
                const key = `${gate[0]},${gate[1]}`;
                if (this.spawned < this.config.NUM_AGENTS && !occupied.has(key)) {
                    const agent = new Agent(this.grid, gate, this.assigned, this.seatBlocks, this.blockToCorridorCells, this.config);
                    this.agents.push(agent);
                    this.spawned++;
                    occupied.add(key);
                    
                    // Reserve destination for standing agents
                    if (agent.willStand && agent.seat) {
                        this.grid[agent.seat[0]][agent.seat[1]] = CELL_TYPES.STANDING;
                    }
                }
            }
            
            // Update agents
            this.agents.forEach(agent => {
                if (!agent.seated && !agent.standing) {
                    agent.update(this.grid);
                }
            });
            
            this.time++;
            
            // Update chart data
            const seated = this.agents.filter(a => a.seated).length;
            const standing = this.agents.filter(a => a.standing).length;
            this.chartData.time.push(this.time);
            this.chartData.seated.push(seated);
            this.chartData.standing.push(standing);
            
            // Check completion
            const allSettled = this.agents.every(a => a.seated || a.standing);
            if ((allSettled && this.spawned >= this.config.NUM_AGENTS) || this.time >= this.config.MAX_TIME) {
                this.completed = true;
                return { completed: true, seated, standing };
            }
            
            return { completed: false, seated, standing, moving: this.agents.filter(a => !a.seated && !a.standing).length };
        } catch (error) {
            console.error('Simulation update error:', error);
            this.completed = true;
            return { completed: true, error: true };
        }
    }

    getStats() {
        const seated = this.agents.filter(a => a.seated).length;
        const standing = this.agents.filter(a => a.standing).length;
        const moving = this.agents.filter(a => !a.seated && !a.standing).length;
        const seatedPercent = this.spawned > 0 ? ((seated / this.spawned) * 100).toFixed(1) : 0;
        
        return {
            time: this.time,
            spawned: this.spawned,
            seated,
            standing,
            moving,
            seatedPercent
        };
    }
}

// ===== UI CONTROLLER ===== //

class UIController {
    constructor(configManager) {
        this.configManager = configManager;
        this.simulation = null;
        this.renderer = null;
        this.animationId = null;
        this.isRunning = false;
        this.isBuilt = false;
        
        this.initializeElements();
        this.setupEventListeners();
    }

    initializeElements() {
        this.elements = {
            canvas: document.getElementById('simCanvas'),
            chartCanvas: document.getElementById('seatingChart'),
            buildBtn: document.getElementById('buildBtn'),
            startBtn: document.getElementById('startBtn'),
            pauseBtn: document.getElementById('pauseBtn'),
            resetBtn: document.getElementById('resetBtn'),
            completionMsg: document.getElementById('completionMsg'),
            stats: document.getElementById('stats')
        };
        
        // Initialize renderer
        if (this.elements.canvas && this.elements.chartCanvas) {
            this.renderer = new Renderer(this.elements.canvas, this.elements.chartCanvas);
            this.updateCanvasSize();
        }
    }

    updateCanvasSize() {
        const config = this.configManager.config;
        this.elements.canvas.width = config.COLS * VISUAL_CONFIG.CELL_SIZE;
        this.elements.canvas.height = config.ROWS * VISUAL_CONFIG.CELL_SIZE;
    }

    setupEventListeners() {
        // Slider controls with debouncing
        this.setupSliderControl('numAgents', 'agentsValue', 'NUM_AGENTS');
        this.setupSliderControl('speed', 'speedValue', 'SPEED', v => v + 'ms');
        this.setupSliderControl('maxTime', 'maxTimeValue', 'MAX_TIME');
        this.setupSliderControl('numBlocks', 'blocksValue', 'NUM_BLOCKS');
        this.setupSliderControl('corridorWidth', 'corridorValue', 'CORRIDOR_WIDTH');
        this.setupSliderControl('socialDistance', 'socialValue', 'SOCIAL_DISTANCE');
        this.setupSliderControl('backPref', 'backValue', 'BACK_PREF');
        
        // Checkbox controls
        this.setupCheckboxControl('assignedSeats', 'FEATURE_ASSIGNED_SEATS');
        this.setupCheckboxControl('colorByBlock', 'FEATURE_COLOR_BY_BLOCK');
        
        // Button controls
        this.elements.buildBtn.addEventListener('click', () => this.build());
        this.elements.startBtn.addEventListener('click', () => this.start());
        this.elements.pauseBtn.addEventListener('click', () => this.pause());
        this.elements.resetBtn.addEventListener('click', () => this.reset());
    }

    setupSliderControl(sliderId, displayId, configKey, formatter = v => v) {
        const slider = document.getElementById(sliderId);
        const display = document.getElementById(displayId);
        
        if (!slider || !display) return;
        
        const debouncedUpdate = Utils.debounce((value) => {
            this.configManager.set(configKey, parseInt(value));
        }, 100);
        
        slider.addEventListener('input', (e) => {
            const value = parseInt(e.target.value);
            display.textContent = formatter(value);
            debouncedUpdate(value);
        });
    }

    setupCheckboxControl(checkboxId, configKey) {
        const checkbox = document.getElementById(checkboxId);
        if (!checkbox) return;
        
        checkbox.addEventListener('change', (e) => {
            this.configManager.set(configKey, e.target.checked);
        });
    }

    build() {
        try {
            this.simulation = new SimulationEngine(this.configManager.config);
            if (!this.simulation.initialize()) {
                this.showError('Failed to initialize simulation');
                return;
            }
            
            this.updateCanvasSize();
            this.draw();
            this.isBuilt = true;
            
            // Update button states
            this.elements.startBtn.disabled = false;
            this.elements.buildBtn.disabled = true;
            this.elements.completionMsg.style.display = 'none';
            
            console.log('Conference room built successfully');
        } catch (error) {
            console.error('Build error:', error);
            this.showError('Error building conference room');
        }
    }

    start() {
        if (!this.isBuilt) {
            this.build();
        }
        
        if (!this.isRunning && this.simulation) {
            this.isRunning = true;
            this.elements.pauseBtn.disabled = false;
            this.animate();
        }
    }

    pause() {
        this.isRunning = false;
        if (this.animationId) {
            clearTimeout(this.animationId);
            this.animationId = null;
        }
        this.elements.pauseBtn.disabled = true;
    }

    reset() {
        this.pause();
        this.simulation = null;
        this.isBuilt = false;
        
        // Clear displays
        if (this.renderer) {
            this.renderer.ctx.clearRect(0, 0, this.elements.canvas.width, this.elements.canvas.height);
            const container = this.elements.chartCanvas.parentElement;
            this.renderer.chartCtx.clearRect(0, 0, container.clientWidth, 400);
        }
        
        // Reset UI
        this.elements.completionMsg.style.display = 'none';
        this.elements.startBtn.disabled = true;
        this.elements.pauseBtn.disabled = true;
        this.elements.buildBtn.disabled = false;
        this.elements.stats.textContent = 'Click "Build Conference Room" to start';
        
        console.log('Reset complete');
    }

    animate() {
        if (!this.isRunning || !this.simulation) return;
        
        try {
            const result = this.simulation.update();
            this.draw();
            
            if (result.completed) {
                this.showCompletionMessage(result);
                this.pause();
            } else {
                this.animationId = setTimeout(() => this.animate(), this.configManager.config.SPEED);
            }
        } catch (error) {
            console.error('Animation error:', error);
            this.pause();
            this.showError('Simulation error occurred');
        }
    }

    draw() {
        if (!this.simulation || !this.renderer) return;
        
        try {
            this.renderer.drawGrid(this.simulation.grid, this.simulation.agents, this.configManager.config);
            this.renderer.drawChart(this.simulation.chartData);
            this.updateStats();
        } catch (error) {
            console.error('Drawing error:', error);
        }
    }

    updateStats() {
        if (!this.simulation) return;
        
        const stats = this.simulation.getStats();
        this.elements.stats.textContent = 
            `Time: ${stats.time} | Arrived: ${stats.spawned} | Moving: ${stats.moving} | ` +
            `Seated: ${stats.seated} (${stats.seatedPercent}%) | Standing: ${stats.standing}`;
    }

    showCompletionMessage(result) {
        if (result.error) {
            this.elements.completionMsg.textContent = '❌ Simulation encountered an error';
            this.elements.completionMsg.style.background = '#fc8181';
        } else {
            const seatedPercent = this.simulation.spawned > 0 ? 
                ((result.seated / this.simulation.spawned) * 100).toFixed(1) : 0;
            this.elements.completionMsg.textContent = 
                `✅ Simulation Complete! Time: ${this.simulation.time} ticks | ` +
                `${result.seated} seated (${seatedPercent}%), ${result.standing} standing`;
            this.elements.completionMsg.style.background = '#48bb78';
        }
        this.elements.completionMsg.style.display = 'block';
    }

    showError(message) {
        this.elements.completionMsg.textContent = `❌ ${message}`;
        this.elements.completionMsg.style.background = '#fc8181';
        this.elements.completionMsg.style.display = 'block';
    }
}

// ===== INITIALIZATION ===== //

document.addEventListener('DOMContentLoaded', function() {
    try {
        // Initialize configuration manager
        const configManager = new ConfigManager();
        
        // Initialize UI controller
        const uiController = new UIController(configManager);
        
        // Initial reset to set up UI state
        uiController.reset();
        
        console.log('Conference Seating Simulation initialized successfully');
    } catch (error) {
        console.error('Initialization error:', error);
        document.body.innerHTML = '<div style="text-align: center; padding: 50px; color: red;">Error initializing simulation. Please refresh the page.</div>';
    }
});