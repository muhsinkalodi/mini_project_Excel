firebase.auth().signInWithEmailAndPassword(email, password)
  .then((userCredential) => {
    userCredential.user.getIdToken().then((idToken) => {
      fetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idToken: idToken })
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          window.location.href = "/home";
        } else {
          alert(data.error);
        }
      });
    });
  })
  .catch(error => console.error('Error:', error));
