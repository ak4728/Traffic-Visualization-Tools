// Debug script to test restart functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('Debug script loaded');
    
    // Test if restart button exists
    const restartBtn = document.getElementById('restartBtn');
    console.log('Restart button found:', restartBtn);
    
    if (restartBtn) {
        console.log('Button disabled:', restartBtn.disabled);
        console.log('Button display:', restartBtn.style.display);
        console.log('Button onclick:', restartBtn.onclick);
        
        // Add debug click handler
        restartBtn.addEventListener('click', function(e) {
            console.log('DEBUG: Restart button clicked!', e);
            console.log('Button state - disabled:', this.disabled, 'display:', this.style.display);
        });
    }
});