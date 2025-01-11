// console.log('Script loaded successfully.');

function checkAgreement(event) {
    // console.log('checkAgreement function called');
    const checkbox = document.getElementById('agree');
    if (!checkbox) {
        // console.error('Checkbox element not found');
        return;
    }
    // console.log('Checkbox element found');
    if (!checkbox.checked) {
        event.preventDefault();
        // console.log('Checkbox not checked, preventing default action');
        alert('You must agree to the Terms of Service and Privacy Policy to proceed.');
    } else {
        // console.log('Checkbox checked, proceeding with default action');
    }
}

// Attach the function to the click event of the login button
document.addEventListener('DOMContentLoaded', function() {
    const loginButton = document.querySelector('.login-btn');
    if (loginButton) {
        loginButton.addEventListener('click', checkAgreement);
        // console.log('Event listener added to login button');
    } else {
        // console.error('Login button not found');
    }
});