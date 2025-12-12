// ===== CONFERENCE SEATING SIMULATION ===== //
// Version 2.5.5 - Added seating speed tracking and reporting

// ===== CONSTANTS & CONFIGURATION ===== //

const VERSION = '2.5.5';

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
            FEATURE_ASSIGNED_SEATS: true,
            FEATURE_COLOR_BY_BLOCK: true,
            NUM_AGENTS: 384,
            SPEED: 20,
            MAX_TIME: 500,
            SOCIAL_DISTANCE: 3,
            BACK_PREF: 3,
            AISLE_PREF: 2
        };
        this.listeners = new Set();
        // Calculate initial corridor width
        this.calculateCorridorWidth();
    }

    set(key, value) {
        if (this.validate(key, value)) {
            this.config[key] = value;
            
            // Debug: Log aisle preference changes
            if (key === 'AISLE_PREF') {
                console.log(`🎛️ AISLE_PREF updated to: ${value}`);
            }
            
            // Recalculate corridor width when blocks change
            if (key === 'NUM_BLOCKS') {
                this.calculateCorridorWidth();
            }
            
            this.notifyListeners(key, value);
        }
    }
    
    calculateCorridorWidth() {
        const totalCols = this.config.COLS;
        const numBlocks = this.config.NUM_BLOCKS;
        const numCorridors = numBlocks + 1;
        
        // Calculate width so that seats + corridors = total columns
        // Let's aim for equal distribution: seats per block should be similar
        // Formula: totalCols = (numBlocks * seatsPerBlock) + (numCorridors * corridorWidth)
        
        // Try different corridor widths to find the best fit
        let bestCorridorWidth = 2;
        let bestSeatsPerBlock = 0;
        
        for (let corridorWidth = 2; corridorWidth <= 6; corridorWidth++) {
            const totalCorridorSpace = numCorridors * corridorWidth;
            const remainingForSeats = totalCols - totalCorridorSpace;
            const seatsPerBlock = Math.floor(remainingForSeats / numBlocks);
            
            // Prefer configurations that give more seats per block while keeping corridor width reasonable
            if (seatsPerBlock > bestSeatsPerBlock && remainingForSeats >= 0) {
                bestCorridorWidth = corridorWidth;
                bestSeatsPerBlock = seatsPerBlock;
            }
        }
        
        this.config.CORRIDOR_WIDTH = bestCorridorWidth;
        console.log(`Calculated corridor width: ${bestCorridorWidth} for ${numBlocks} blocks (${bestSeatsPerBlock} seats per block)`);
        
        // Update UI display
        const display = document.getElementById('calculatedCorridorWidth');
        if (display) {
            display.textContent = bestCorridorWidth;
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
            SOCIAL_DISTANCE: v => v >= 0 && v <= 5,
            BACK_PREF: v => v >= 0 && v <= 5,
            AISLE_PREF: v => v >= 0 && v <= 5
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
        
        console.log(`Seat calculation: ${cols} cols - ${numBlocks + 1} corridors * ${corridorWidth} width = ${totalSeat} seats total`);
        console.log(`Block width: ${blockWidth} seats per block`);
        
        for (let i = 0; i < numBlocks; i++) {
            const start = corridorWidth + i * (blockWidth + corridorWidth);
            const end = start + blockWidth - 1;
            blocks[i] = [start, end];
            console.log(`Block ${i}: cols ${start}-${end} (width: ${end - start + 1})`);
        }
        
        return blocks;
    }

    static generateCorridorSegments(cols, seatBlocks, corridorWidth) {
        const segments = [];
        const leftMargin = Array.from({length: corridorWidth}, (_, i) => i);
        segments.push(leftMargin);
        
        const numBlocks = Object.keys(seatBlocks).length;
        for (let i = 0; i < numBlocks; i++) {
            const end = seatBlocks[i][1];
            const seg = Array.from({length: corridorWidth}, (_, j) => end + 1 + j);
            // Make sure we don't exceed column bounds
            const validSeg = seg.filter(col => col < cols);
            if (validSeg.length > 0) {
                segments.push(validSeg);
            }
        }
        
        console.log(`Generated ${segments.length} corridor segments for ${numBlocks} blocks:`, segments.map(seg => `[${seg.join(',')}]`).join(', '));
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

    static pickBlockBasedOnGate(gateCol, numBlocks, gates) {
        // Dynamic block selection based on gate position and number of blocks
        if (!gates || gates.length === 0 || numBlocks <= 0) {
            return 0; // fallback
        }
        
        // Find which gate this column is closest to
        const gateIndex = gates.findIndex(gate => gate[1] === gateCol);
        
        if (gateIndex === -1) {
            // If not an exact gate match, find closest gate
            const closestGateIndex = gates.reduce((closest, gate, index) => {
                const currentDistance = Math.abs(gate[1] - gateCol);
                const closestDistance = Math.abs(gates[closest][1] - gateCol);
                return currentDistance < closestDistance ? index : closest;
            }, 0);
            
            // Assign blocks around the closest gate
            const blockSpan = Math.max(1, Math.floor(numBlocks / gates.length));
            const baseBlock = Math.min(closestGateIndex * blockSpan, numBlocks - 1);
            const possibleBlocks = [];
            const weights = [];
            
            // Add the primary block
            possibleBlocks.push(baseBlock);
            weights.push(0.6);
            
            // Add adjacent blocks with lower weights
            if (baseBlock > 0) {
                possibleBlocks.push(baseBlock - 1);
                weights.push(0.2);
            }
            if (baseBlock < numBlocks - 1) {
                possibleBlocks.push(baseBlock + 1);
                weights.push(0.2);
            }
            
            return Utils.weightedChoice(possibleBlocks, weights);
        }
        
        // Original logic adapted for dynamic blocks
        const blockSpan = numBlocks / gates.length;
        const baseBlock = Math.floor(gateIndex * blockSpan);
        
        // Create weighted choices around the base block
        const possibleBlocks = [];
        const weights = [];
        
        // Primary block gets highest weight
        if (baseBlock < numBlocks) {
            possibleBlocks.push(baseBlock);
            weights.push(0.6);
        }
        
        // Adjacent blocks get lower weights
        if (baseBlock + 1 < numBlocks) {
            possibleBlocks.push(baseBlock + 1);
            weights.push(0.3);
        }
        
        if (baseBlock > 0 && possibleBlocks.length < 2) {
            possibleBlocks.push(baseBlock - 1);
            weights.push(0.1);
        }
        
        console.log(`Gate ${gateCol} -> blocks [${possibleBlocks.join(',')}] with weights [${weights.map(w => w.toFixed(1)).join(',')}]`);
        return Utils.weightedChoice(possibleBlocks, weights);
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
            
            // STEP 1: First select preferred rows based on back preference
            const availableRows = [];
            for (let r = SIM_CONSTANTS.SEAT_ROWS.START; r < SIM_CONSTANTS.SEAT_ROWS.END; r++) {
                if (this.rowOccupancy(grid, r, c0, c1) >= rowThr) continue;
                
                // Check if row has any available seats
                let hasSeats = false;
                for (let c = c0; c <= c1; c++) {
                    const key = `${r},${c}`;
                    if (grid[r][c] === CELL_TYPES.SEAT && !assigned.has(key)) {
                        hasSeats = true;
                        break;
                    }
                }
                if (hasSeats) {
                    availableRows.push(r);
                }
            }
            
            if (availableRows.length === 0) return null;

            // Optional hard exclusion of front rows based on back preference
            // Goal: when BACK_PREF is moderate/high, many agents simply won't sit in the very front rows
            let candidateRows = availableRows;
            if (config.BACK_PREF > 0) {
                const startRow = SIM_CONSTANTS.SEAT_ROWS.START;
                // Map BACK_PREF (0-5) to how many front rows to avoid when possible
                // 0 → 0, 1 → 0, 2-3 → 1 row, 4-5 → 2 rows
                const banFrontRows = config.BACK_PREF >= 4 ? 2 : (config.BACK_PREF >= 2 ? 1 : 0);
                if (banFrontRows > 0) {
                    const filtered = availableRows.filter(r => (r - startRow) >= banFrontRows);
                    if (filtered.length > 0) {
                        candidateRows = filtered;
                        if (Math.random() < 0.2) {
                            console.log(`🚫 Front rows banned=${banFrontRows}; candidates=[${candidateRows.join(',')}] from available=[${availableRows.join(',')}]`);
                        }
                    }
                }
                // Backend-only probabilistic front aversion: some agents simply won't sit in absolute front rows
                // Compute a probability from BACK_PREF; higher back pref => more likely to avoid front row entirely
                if (candidateRows.length > 0) {
                    const sorted = [...candidateRows].sort((a,b)=>a-b);
                    const frontMost = sorted[0];
                    const secondFront = sorted[1];
                    const pAvoidFront = Math.min(0.15 + 0.15 * config.BACK_PREF, 0.85); // 0.15..0.85
                    const pAvoidSecond = config.BACK_PREF >= 4 ? 0.35 : (config.BACK_PREF >= 3 ? 0.2 : 0.0);
                    let probFiltered = candidateRows;
                    if (Math.random() < pAvoidFront) {
                        const tmp = probFiltered.filter(r => r !== frontMost);
                        if (tmp.length > 0) probFiltered = tmp;
                    }
                    if (probFiltered.length > 1 && secondFront !== undefined && Math.random() < pAvoidSecond) {
                        const tmp2 = probFiltered.filter(r => r !== secondFront);
                        if (tmp2.length > 0) probFiltered = tmp2;
                    }
                    // Only adopt probabilistic filtering if we still have options
                    if (probFiltered.length > 0 && probFiltered.length !== candidateRows.length) {
                        if (Math.random() < 0.2) {
                            console.log(`🙅 Front aversion applied → rows=[${probFiltered.join(',')}] (from ${candidateRows.join(',')})`);
                        }
                        candidateRows = probFiltered;
                    }
                }
            }
            
            // Apply back row preference to select which row to focus on
            let chosenRow;
            if (config.BACK_PREF > 0) {
                const rowWeights = candidateRows.map(r => {
                    const rowFromFront = r - SIM_CONSTANTS.SEAT_ROWS.START; // 0 at front, increases toward back
                    // Ensure no preference when BACK_PREF=0, and strong bias when high
                    // Back rows (larger rowFromFront) receive higher weights
                    return 1 + config.BACK_PREF * Math.pow(2.0, rowFromFront);
                });
                chosenRow = Utils.weightedChoice(candidateRows, rowWeights);
                
                if (config.BACK_PREF > 3 && Math.random() < 0.25) {
                    const dbg = candidateRows.map((r,i)=>`${r}:${rowWeights[i].toFixed(1)}`).join(', ');
                    console.log(`🎯 ROW SELECTION: rows[w]=${dbg} ⇒ chose ${chosenRow} (BACK_PREF=${config.BACK_PREF})`);
                }
            } else {
                // No back preference - choose randomly
                chosenRow = candidateRows[Math.floor(Math.random() * candidateRows.length)];
            }
            
            // STEP 2: Within chosen row, find seats and apply aisle + social distance preferences
            const validSeats = [];
            for (let c = c0; c <= c1; c++) {
                const key = `${chosenRow},${c}`;
                if (grid[chosenRow][c] === CELL_TYPES.SEAT && !assigned.has(key)) {
                    let seatWeight = 1; // Base weight
                    
                    // Apply aisle preference (edge seats get bonus)
                    const distFromEdge = Math.min(c - c0, c1 - c);
                    if (distFromEdge <= 1 && config.AISLE_PREF > 0) {
                        seatWeight += config.AISLE_PREF * 3; // Aisle bonus
                    }
                    
                    // Apply social distancing (avoid crowded seats)
                    const adjacentCount = this.countAdjacentSeated(grid, [chosenRow, c]);
                    const socialBonus = (8 - adjacentCount) * config.SOCIAL_DISTANCE;
                    seatWeight += socialBonus;
                    
                    // Debug logging
                    if (Math.random() < 0.05) {
                        const aisleBonus = distFromEdge <= 1 ? config.AISLE_PREF * 3 : 0;
                        console.log(`💺 SEAT [${chosenRow},${c}]: aisle=${aisleBonus}, social=${socialBonus}, total=${seatWeight}`);
                    }
                    
                    validSeats.push([[chosenRow, c], Math.max(seatWeight, 0.01)]);
                }
            }
            
            if (validSeats.length === 0) return null;
            
            // STEP 3: Choose final seat within the chosen row
            const seats = validSeats.map(v => v[0]);
            const weights = validSeats.map(v => v[1]);
            const chosenSeat = Utils.weightedChoice(seats, weights);
            
            if (config.BACK_PREF > 3 && Math.random() < 0.1) {
                console.log(`✅ FINAL CHOICE: Row ${chosenRow}, Seat [${chosenSeat[0]},${chosenSeat[1]}]`);
            }
            
            return chosenSeat;
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
    constructor(grid, spawn, assigned, seatBlocks, blockToCorridorCells, config, gates = null) {
        try {
            this.pos = spawn;
            this.seated = false;
            this.standing = false;
            this.willStand = false;
            
            const gateC = spawn[1];
            const numBlocks = Object.keys(seatBlocks).length;
            this.block = PathfindingEngine.pickBlockBasedOnGate(gateC, numBlocks, gates);
            
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
    constructor(canvas, chartCanvas, seatedCountChart, percentDistChart, speedChart) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.chartCanvas = chartCanvas;
        this.chartCtx = chartCanvas.getContext('2d');
        this.seatedCountChart = seatedCountChart;
        this.seatedCountCtx = seatedCountChart ? seatedCountChart.getContext('2d') : null;
        this.percentDistChart = percentDistChart;
        this.percentDistCtx = percentDistChart ? percentDistChart.getContext('2d') : null;
        this.speedChart = speedChart;
        this.speedCtx = speedChart ? speedChart.getContext('2d') : null;
        
        this.setupCanvases();
    }

    setupCanvases() {
        try {
            // Set chart canvas to match container size with high DPI
            this.resizeChart();
            this.resizeHistoryCharts();
            window.addEventListener('resize', () => {
                this.resizeChart();
                this.resizeHistoryCharts();
            });
        } catch (error) {
            console.error('Canvas setup error:', error);
        }
    }

    resizeHistoryCharts() {
        try {
            const dpr = window.devicePixelRatio || 1;
            
            // Resize seated count chart
            if (this.seatedCountChart && this.seatedCountCtx) {
                const container = this.seatedCountChart.parentElement;
                this.seatedCountChart.width = 400 * dpr;
                this.seatedCountChart.height = 200 * dpr;
                this.seatedCountChart.style.width = '400px';
                this.seatedCountChart.style.height = '200px';
                this.seatedCountCtx.scale(dpr, dpr);
            }
            
            // Resize percent distribution chart
            if (this.percentDistChart && this.percentDistCtx) {
                const container = this.percentDistChart.parentElement;
                this.percentDistChart.width = 400 * dpr;
                this.percentDistChart.height = 200 * dpr;
                this.percentDistChart.style.width = '400px';
                this.percentDistChart.style.height = '200px';
                this.percentDistCtx.scale(dpr, dpr);
            }
            
            // Resize speed chart
            if (this.speedChart && this.speedCtx) {
                const container = this.speedChart.parentElement;
                this.speedChart.width = 400 * dpr;
                this.speedChart.height = 200 * dpr;
                this.speedChart.style.width = '400px';
                this.speedChart.style.height = '200px';
                this.speedCtx.scale(dpr, dpr);
            }
        } catch (error) {
            console.error('History chart resize error:', error);
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

    drawStage() {
        // Draw stage at the very TOP - rows 0-2
        const stageHeight = VISUAL_CONFIG.CELL_SIZE * 3;
        
        // Bright red stage
        this.ctx.fillStyle = '#FF0000';
        this.ctx.fillRect(0, 0, this.canvas.width, stageHeight);
        
        // Black border for visibility
        this.ctx.strokeStyle = '#000000';
        this.ctx.lineWidth = 4;
        this.ctx.strokeRect(0, 0, this.canvas.width, stageHeight);
        
        // White text
        this.ctx.fillStyle = 'white';
        this.ctx.font = 'bold 18px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.fillText('🎭 CONFERENCE STAGE 🎭', this.canvas.width / 2, stageHeight / 2 + 6);
        this.ctx.textAlign = 'start';
        
        console.log('🎭 Stage drawn at (0,0) with height', stageHeight);
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

    drawHistoryCharts(runHistory) {
        if (!runHistory || runHistory.length === 0 || !this.seatedCountCtx || !this.percentDistCtx) return;
        
        this.drawSeatedCountChart(runHistory);
        this.drawPercentDistributionChart(runHistory);
        
        if (this.speedCtx) {
            this.drawSpeedChart(runHistory);
        }
    }

    drawSeatedCountChart(runHistory) {
        const canvas = this.seatedCountChart;
        const ctx = this.seatedCountCtx;
        const displayWidth = 400;
        const displayHeight = 200;
        
        ctx.clearRect(0, 0, displayWidth, displayHeight);
        
        const padding = 40;
        const chartWidth = displayWidth - 2 * padding;
        const chartHeight = displayHeight - 2 * padding;
        
        const seatedCounts = runHistory.map(run => run.seated);
        const maxSeated = Math.max(...seatedCounts, 100);
        const minSeated = Math.min(...seatedCounts, 0);
        
        // Round to nearest 20-person increment
        const maxRounded = Math.ceil(maxSeated / 20) * 20;
        const minRounded = Math.floor(minSeated / 20) * 20;
        const range = maxRounded - minRounded || 20;
        
        // Background
        ctx.fillStyle = '#f9f9f9';
        ctx.fillRect(0, 0, displayWidth, displayHeight);
        
        // Grid lines
        ctx.strokeStyle = '#e0e0e0';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 5; i++) {
            const y = padding + (i * chartHeight) / 5;
            ctx.beginPath();
            ctx.moveTo(padding, y);
            ctx.lineTo(padding + chartWidth, y);
            ctx.stroke();
        }
        
        // Draw bars
        const barWidth = chartWidth / runHistory.length;
        runHistory.forEach((run, index) => {
            const barHeight = ((run.seated - minRounded) / range) * chartHeight;
            const x = padding + index * barWidth + barWidth * 0.1;
            const y = padding + chartHeight - barHeight;
            
            ctx.fillStyle = '#4CAF50';
            ctx.fillRect(x, y, barWidth * 0.8, barHeight);
            
            // Labels
            ctx.fillStyle = '#333';
            ctx.font = '10px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(run.seated.toString(), x + barWidth * 0.4, y - 5);
        });
        
        // Axes
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(padding, padding);
        ctx.lineTo(padding, padding + chartHeight);
        ctx.lineTo(padding + chartWidth, padding + chartHeight);
        ctx.stroke();
        
        // Y-axis labels with 20-person increments
        ctx.fillStyle = '#666';
        ctx.font = '10px Arial';
        ctx.textAlign = 'right';
        for (let i = 0; i <= 5; i++) {
            const value = minRounded + (range / 5) * (5 - i);
            const y = padding + (i * chartHeight) / 5;
            ctx.fillText(value.toString(), padding - 5, y + 3);
        }
    }

    drawPercentDistributionChart(runHistory) {
        const canvas = this.percentDistChart;
        const ctx = this.percentDistCtx;
        const displayWidth = 400;
        const displayHeight = 200;
        
        ctx.clearRect(0, 0, displayWidth, displayHeight);
        
        const padding = 40;
        const chartWidth = displayWidth - 2 * padding;
        const chartHeight = displayHeight - 2 * padding;
        
        const percentages = runHistory.map(run => parseFloat(run.seatedPercent));
        
        // Create distribution bins with 5% increments (0-5%, 5-10%, ..., 95-100%)
        const bins = Array(20).fill(0);
        percentages.forEach(percent => {
            const binIndex = Math.min(19, Math.floor(percent / 5));
            bins[binIndex]++;
        });
        
        const maxCount = Math.max(...bins, 1);
        
        // Background
        ctx.fillStyle = '#f9f9f9';
        ctx.fillRect(0, 0, displayWidth, displayHeight);
        
        // Grid lines
        ctx.strokeStyle = '#e0e0e0';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 5; i++) {
            const y = padding + (i * chartHeight) / 5;
            ctx.beginPath();
            ctx.moveTo(padding, y);
            ctx.lineTo(padding + chartWidth, y);
            ctx.stroke();
        }
        
        // Draw distribution bars
        const barWidth = chartWidth / 20;
        bins.forEach((count, index) => {
            const barHeight = (count / maxCount) * chartHeight;
            const x = padding + index * barWidth + barWidth * 0.1;
            const y = padding + chartHeight - barHeight;
            
            ctx.fillStyle = '#2196F3';
            ctx.fillRect(x, y, barWidth * 0.8, barHeight);
            
            // Labels - only show every 4th label to avoid crowding
            if (index % 4 === 0) {
                ctx.fillStyle = '#333';
                ctx.font = '8px Arial';
                ctx.textAlign = 'center';
                ctx.fillText(`${index * 5}%`, x + barWidth * 0.4, padding + chartHeight + 15);
            }
            
            if (count > 0) {
                ctx.fillStyle = '#333';
                ctx.font = '8px Arial';
                ctx.textAlign = 'center';
                ctx.fillText(count.toString(), x + barWidth * 0.4, y - 5);
            }
        });
        
        // Axes
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(padding, padding);
        ctx.lineTo(padding, padding + chartHeight);
        ctx.lineTo(padding + chartWidth, padding + chartHeight);
        ctx.stroke();
        
        // Y-axis labels
        ctx.fillStyle = '#666';
        ctx.font = '10px Arial';
        ctx.textAlign = 'right';
        for (let i = 0; i <= 5; i++) {
            const value = Math.round((maxCount / 5) * (5 - i));
            const y = padding + (i * chartHeight) / 5;
            ctx.fillText(value.toString(), padding - 5, y + 3);
        }
    }

    drawSpeedChart(runHistory) {
        const canvas = this.speedChart;
        const ctx = this.speedCtx;
        const displayWidth = 400;
        const displayHeight = 200;
        
        ctx.clearRect(0, 0, displayWidth, displayHeight);
        
        const padding = 40;
        const chartWidth = displayWidth - 2 * padding;
        const chartHeight = displayHeight - 2 * padding;
        
        const speeds = runHistory.map(run => parseFloat(run.seatingSpeed));
        const maxSpeed = Math.max(...speeds, 1);
        const minSpeed = Math.min(...speeds, 0);
        
        // Round to reasonable increments for speed (0.5 people/tick increments)
        const maxRounded = Math.ceil(maxSpeed * 2) / 2;
        const minRounded = Math.floor(minSpeed * 2) / 2;
        const range = maxRounded - minRounded || 0.5;
        
        // Background
        ctx.fillStyle = '#f9f9f9';
        ctx.fillRect(0, 0, displayWidth, displayHeight);
        
        // Grid lines
        ctx.strokeStyle = '#e0e0e0';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 5; i++) {
            const y = padding + (i * chartHeight) / 5;
            ctx.beginPath();
            ctx.moveTo(padding, y);
            ctx.lineTo(padding + chartWidth, y);
            ctx.stroke();
        }
        
        // Draw bars
        const barWidth = chartWidth / runHistory.length;
        runHistory.forEach((run, index) => {
            const speed = parseFloat(run.seatingSpeed);
            const barHeight = ((speed - minRounded) / range) * chartHeight;
            const x = padding + index * barWidth + barWidth * 0.1;
            const y = padding + chartHeight - barHeight;
            
            ctx.fillStyle = '#FF9800';
            ctx.fillRect(x, y, barWidth * 0.8, barHeight);
            
            // Labels
            ctx.fillStyle = '#333';
            ctx.font = '10px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(run.seatingSpeed, x + barWidth * 0.4, y - 5);
        });
        
        // Axes
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(padding, padding);
        ctx.lineTo(padding, padding + chartHeight);
        ctx.lineTo(padding + chartWidth, padding + chartHeight);
        ctx.stroke();
        
        // Y-axis labels
        ctx.fillStyle = '#666';
        ctx.font = '10px Arial';
        ctx.textAlign = 'right';
        for (let i = 0; i <= 5; i++) {
            const value = (minRounded + (range / 5) * (5 - i)).toFixed(1);
            const y = padding + (i * chartHeight) / 5;
            ctx.fillText(value, padding - 5, y + 3);
        }
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
            
            // Debug: Log seat blocks and corridors
            console.log(`Blocks: ${this.config.NUM_BLOCKS}, SeatBlocks:`, this.seatBlocks);
            console.log(`CorridorSegs (${this.corridorSegs.length}):`, this.corridorSegs);
            
            this.blockToCorridorCells = {};
            for (let i = 0; i < this.config.NUM_BLOCKS; i++) {
                const availableCorridors = [];
                
                // Add left corridor (always available for block i)
                if (this.corridorSegs[i]) {
                    availableCorridors.push(this.corridorSegs[i]);
                }
                
                // Add right corridor (available if it exists)
                if (this.corridorSegs[i + 1]) {
                    availableCorridors.push(this.corridorSegs[i + 1]);
                }
                
                // For the rightmost block, if it's missing its right corridor,
                // let it also use the corridor from the previous block
                if (availableCorridors.length === 1 && i === this.config.NUM_BLOCKS - 1) {
                    // Allow rightmost block to use the previous corridor too
                    if (this.corridorSegs[i - 1]) {
                        availableCorridors.unshift(this.corridorSegs[i - 1]);
                    }
                }
                
                this.blockToCorridorCells[i] = availableCorridors;
                console.log(`Block ${i}: ${availableCorridors.length} corridor(s) available`);
            }
            
            console.log('BlockToCorridorCells mapping:', this.blockToCorridorCells);
            
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
            
            // Spawn new agents with realistic arrival patterns
            for (const gate of this.gates) {
                const key = `${gate[0]},${gate[1]}`;
                if (this.spawned < this.config.NUM_AGENTS && !occupied.has(key)) {
                    // Early arrivals prefer back seats (more back preference)
                    const arrivalRatio = this.spawned / this.config.NUM_AGENTS;
                    const backPrefMultiplier = arrivalRatio < 0.3 ? 1.5 : // Early arrivals
                                              arrivalRatio < 0.7 ? 1.0 : // Mid arrivals
                                              0.5; // Late arrivals prefer front
                    
                    const modifiedConfig = {...this.config};
                    modifiedConfig.BACK_PREF = Math.max(0, this.config.BACK_PREF * backPrefMultiplier);
                    
                    const agent = new Agent(this.grid, gate, this.assigned, this.seatBlocks, this.blockToCorridorCells, modifiedConfig, this.gates);
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

            // Debug: periodic per-block seating distribution to verify block usage
            if (this.time % 50 === 0) { // roughly every 50 ticks
                const perBlock = {};
                this.agents.forEach(a => {
                    if (a.seated) {
                        perBlock[a.block] = (perBlock[a.block] || 0) + 1;
                    }
                });
                const summary = Object.keys(this.seatBlocks)
                    .map(k => `${k}:${perBlock[k] || 0}`)
                    .join(', ');
                console.log(`🧩 Per-block seated counts @t=${this.time}: ${summary}`);
            }
            
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
        
        // Calculate seating speed (people per tick)
        const seatingSpeed = this.time > 0 ? (seated / this.time).toFixed(2) : '0.00';
        const totalSettled = seated + standing;
        const overallSpeed = this.time > 0 ? (totalSettled / this.time).toFixed(2) : '0.00';
        
        return {
            time: this.time,
            spawned: this.spawned,
            seated,
            standing,
            moving,
            seatedPercent,
            seatingSpeed,
            overallSpeed
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
        this.runHistory = [];
        
        this.initializeElements();
        this.setupEventListeners();
    }

    initializeElements() {
        this.elements = {
            canvas: document.getElementById('simCanvas'),
            chartCanvas: document.getElementById('seatingChart'),
            seatedCountChart: document.getElementById('seatedCountChart'),
            percentDistChart: document.getElementById('percentDistChart'),
            speedChart: document.getElementById('speedChart'),
            buildBtn: document.getElementById('buildBtn'),
            startBtn: document.getElementById('startBtn'),
            pauseBtn: document.getElementById('pauseBtn'),
            restartBtn: document.getElementById('restartBtn'),
            resetBtn: document.getElementById('resetBtn'),
            completionMsg: document.getElementById('completionMsg'),
            stats: document.getElementById('stats'),
            runHistory: document.getElementById('runHistory'),
            historyList: document.getElementById('historyList')
        };
        
        // Initialize renderer
        if (this.elements.canvas && this.elements.chartCanvas) {
            this.renderer = new Renderer(
                this.elements.canvas, 
                this.elements.chartCanvas,
                this.elements.seatedCountChart,
                this.elements.percentDistChart,
                this.elements.speedChart
            );
            this.updateCanvasSize();
        }
    }

    updateCanvasSize() {
        const config = this.configManager.config;
        // Use larger cell size for better visibility
        const cellSize = 12;
        this.elements.canvas.width = config.COLS * cellSize;
        this.elements.canvas.height = config.ROWS * cellSize;
        
        // Update visual config to match
        VISUAL_CONFIG.CELL_SIZE = cellSize;
    }

    setupEventListeners() {
        // Slider controls with debouncing
        this.setupSliderControl('numAgents', 'agentsValue', 'NUM_AGENTS');
        this.setupSliderControl('speed', 'speedValue', 'SPEED', v => v + 'ms');
        this.setupSliderControl('maxTime', 'maxTimeValue', 'MAX_TIME');
        this.setupSliderControl('numBlocks', 'blocksValue', 'NUM_BLOCKS');
        this.setupSliderControl('socialDistance', 'socialValue', 'SOCIAL_DISTANCE');
        this.setupSliderControl('backPref', 'backValue', 'BACK_PREF');
        this.setupSliderControl('aislePref', 'aisleValue', 'AISLE_PREF');
        
        // Checkbox controls
        this.setupCheckboxControl('assignedSeats', 'FEATURE_ASSIGNED_SEATS');
        this.setupCheckboxControl('colorByBlock', 'FEATURE_COLOR_BY_BLOCK');
        
        // Button controls
        this.elements.buildBtn.addEventListener('click', () => this.build());
        this.elements.startBtn.addEventListener('click', () => this.start());
        this.elements.pauseBtn.addEventListener('click', () => this.pause());
        if (this.elements.restartBtn) {
            this.elements.restartBtn.addEventListener('click', () => {
                console.log('Restart button clicked');
                this.restart();
            });
        } else {
            console.error('Restart button not found');
        }
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
        this.elements.restartBtn.style.display = 'none';
        this.elements.startBtn.disabled = true;
        this.elements.pauseBtn.disabled = true;
        this.elements.buildBtn.disabled = false;
        this.elements.stats.textContent = 'Click "Build Conference Room" to start';
        
        console.log('Reset complete');
    }

    restart() {
        if (!this.isBuilt) {
            console.log('Cannot restart: simulation not built');
            return;
        }
        
        console.log('Restarting simulation...');
        
        // Pause current simulation
        this.pause();
        
        try {
            // Rebuild simulation with current config
            this.simulation = new SimulationEngine(this.configManager.config);
            if (!this.simulation.initialize()) {
                this.showError('Failed to restart simulation');
                return;
            }
            
            // Update canvas size for new configuration
            this.updateCanvasSize();
            
            // Clear displays
            if (this.renderer) {
                this.renderer.ctx.clearRect(0, 0, this.elements.canvas.width, this.elements.canvas.height);
                const container = this.elements.chartCanvas.parentElement;
                this.renderer.chartCtx.clearRect(0, 0, container.clientWidth, 400);
            }
            
            // Reset UI state
            this.elements.completionMsg.style.display = 'none';
            this.elements.restartBtn.style.display = 'none';
            this.elements.startBtn.disabled = false;
            this.elements.buildBtn.disabled = true;
            
            // Draw initial state
            this.draw();
            
            // Auto-start the new simulation
            this.start();
            
            console.log('Restart complete - new simulation started');
        } catch (error) {
            console.error('Restart error:', error);
            this.showError('Error restarting simulation');
        }
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
            `Seated: ${stats.seated} (${stats.seatedPercent}%) | Standing: ${stats.standing} | ` +
            `Speed: ${stats.seatingSpeed} people/tick`;
    }

    showCompletionMessage(result) {
        if (result.error) {
            this.elements.completionMsg.textContent = '❌ Simulation encountered an error';
            this.elements.completionMsg.style.background = '#fc8181';
        } else {
            const seatedPercent = this.simulation.spawned > 0 ? 
                ((result.seated / this.simulation.spawned) * 100).toFixed(1) : 0;
            const avgSpeed = this.simulation.time > 0 ? (result.seated / this.simulation.time).toFixed(2) : '0.00';
            this.elements.completionMsg.textContent = 
                `✅ Simulation Complete! Time: ${this.simulation.time} ticks | ` +
                `${result.seated} seated (${seatedPercent}%), ${result.standing} standing | ` +
                `Avg Speed: ${avgSpeed} people/tick`;
            this.elements.completionMsg.style.background = '#48bb78';
        }
        this.elements.completionMsg.style.display = 'block';
        this.elements.restartBtn.style.display = 'inline-block';
        this.elements.restartBtn.disabled = false;
        console.log('Restart button enabled:', !this.elements.restartBtn.disabled);
        
        // Add to run history if successful
        if (!result.error) {
            this.addToRunHistory(result);
        }
    }

    showError(message) {
        this.elements.completionMsg.textContent = `❌ ${message}`;
        this.elements.completionMsg.style.background = '#fc8181';
        this.elements.completionMsg.style.display = 'block';
    }

    addToRunHistory(result) {
        const config = this.configManager.config;
        const seatedPercent = this.simulation.spawned > 0 ? 
            ((result.seated / this.simulation.spawned) * 100).toFixed(1) : 0;
        
        const avgSpeed = this.simulation.time > 0 ? (result.seated / this.simulation.time).toFixed(2) : '0.00';
        
        const historyEntry = {
            timestamp: new Date(),
            time: this.simulation.time,
            seated: result.seated,
            standing: result.standing,
            seatedPercent: seatedPercent,
            seatingSpeed: avgSpeed,
            config: {
                agents: config.NUM_AGENTS,
                blocks: config.NUM_BLOCKS,
                socialDistance: config.SOCIAL_DISTANCE,
                backPref: config.BACK_PREF,
                speed: config.SPEED
            }
        };
        
        this.runHistory.unshift(historyEntry); // Add to beginning
        if (this.runHistory.length > 10) { // Keep only last 10 runs
            this.runHistory.pop();
        }
        
        this.updateRunHistoryDisplay();
        
        // Update history charts
        if (this.renderer) {
            this.renderer.drawHistoryCharts(this.runHistory);
        }
    }

    updateRunHistoryDisplay() {
        if (this.runHistory.length === 0) {
            this.elements.runHistory.style.display = 'none';
            return;
        }
        
        this.elements.runHistory.style.display = 'block';
        this.elements.historyList.innerHTML = '';
        
        this.runHistory.forEach((entry, index) => {
            const item = document.createElement('div');
            item.className = 'history-item';
            
            const timeStr = entry.timestamp.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            
            item.innerHTML = `
                <div>
                    <strong>Run ${this.runHistory.length - index}:</strong> 
                    ${entry.seated} seated (${entry.seatedPercent}%), ${entry.standing} standing
                    <br><small>Speed: ${entry.seatingSpeed} people/tick | Agents: ${entry.config.agents}, Blocks: ${entry.config.blocks}</small>
                </div>
                <div class="history-time">${timeStr}</div>
            `;
            
            this.elements.historyList.appendChild(item);
        });
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
        
        // Set build timestamp for cache busting
        const buildTimeElement = document.getElementById('buildTime');
        if (buildTimeElement) {
            buildTimeElement.textContent = new Date().toLocaleString();
        }
        
        console.log(`Conference Seating Simulation v${VERSION} initialized successfully`);
    } catch (error) {
        console.error('Initialization error:', error);
        document.body.innerHTML = '<div style="text-align: center; padding: 50px; color: red;">Error initializing simulation. Please refresh the page.</div>';
    }
});