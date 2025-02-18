const express = require('express');
const app = express();
const userModel = require("./models/user");
const postModel = require("./models/post");
const cookieParser = require('cookie-parser');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const user = require('./models/user');
const post = require('./models/post');
const flash = require('connect-flash');
const port = 3000;


app.set("view engine", "ejs");
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(cookieParser());




app.get('/', (req, res) => {
    res.redirect('create');
});

app.get('/create', (req, res) => {
    res.render('index');
});

app.post('/create', (req, res) => {
    res.send("user Creation")

});

app.post("/register", async (req, res) => {
    let { email, password, username, name, age } = req.body;

    let user = await userModel.findOne({ email: email });
    if (user) {
        return res.status(500).send("User already exists");

    }
    bcrypt.genSalt(10, (err, salt) => {
        bcrypt.hash(password, salt, async (err, hash) => {
            let user = await userModel.create({
                username: username,
                email,
                age,
                name,
                password: hash
            });
            let tokon = jwt.sign({ email: email, userid: user._id }, "shhh");
            res.cookie("token", tokon);
            console.log({
                username,
                password: hash,
                email,
                age
            })
            // res.send("ok daa settt");
            res.redirect("/login");









        })

    })
    // bcrypt.genSalt(10, (err, salt) => {
    //     if (err) {
    //         return res.status(500).send("Error generating salt");
    //     }
    //     bcrypt.hash(password, salt, async (err, hash) => {
    //         if (err) {
    //             return res.status(500).send("Error hashing password");
    //             console.log("error hasing")
    //         }
    //         let newUser = new userModel({ email, password: hash, username, name, age });
    //         await newUser.save();
    //         res.status(200).send("User registered successfully");
    //         console.log(password)
    //     });
    // });
});

app.get("/login", (req, res) => {
    res.render("login");
})
// Adjust path if necessary

app.post("/login", async (req, res) => {
    let { email, password } = req.body;

    try {
        let user = await userModel.findOne({ email });
        if (!user) return res.status(400).send("User not found");

        bcrypt.compare(password, user.password, (err, result) => {
            if (err) {
                console.log("password not match")
                // Handle any error that occurs during bcrypt compare
                return res.status(500).send("Internal server error");

            }

            if (result) {
                // If passwords match, proceed with the login
                let token = jwt.sign({ email: email, userid: user._id }, "shhh");
                res.cookie("token", token);
                console.log("Login successful");
                return res.status(200).redirect("/profile");

            } else {
                // If passwords don't match, redirect to login page
                return res.status(403).send("Incorrect password  ")

            }
        });

    } catch (error) {
        return res.status(500).send("Error logging in: " + error.message);
    }
});

app.get('/profile', isLoggedIn, async (req, res) => {
    try {
        let user = await userModel.findOne({ email: req.user.email }).populate('posts');
        if (!user) {
            return res.status(404).send("User not found");
        }
        console.log(user);

        res.render('profile', { user: user });

    } catch (error) {
        return res.status(500).send("Error fetching user: " + error.message);
    }



});

app.get('/like/:id', isLoggedIn, async (req, res) => {
    try {
        // Find the post
        let post = await postModel.findOne({ _id: req.params.id }).populate('user');

        // Check if the user has already liked the post
        if (post.likes.indexOf(req.user.userid) !== -1) {
            // User already liked, so remove their ID (unlike)
            post.likes.splice(post.likes.indexOf(req.user.userid), 1);
        } else {
            // User hasn't liked the post yet, so add their ID (like)
            post.likes.push(req.user.userid);
        }

        // Save the post
        await post.save();

        // Redirect back to profile page
        res.redirect('/profile');
    } catch (err) {
        console.error(err);
        res.status(500).send('Server error');
    }
});

app.get('/edit/:id', isLoggedIn, async (req, res) => {
    let post = await postModel.findOne({ _id: req.params.id }).populate('user');
    res.render('edit', { post: post });


});

app.post('/update/:id', isLoggedIn, async (req, res) => {
    let post = await postModel.findOneAndUpdate({ _id: req.params.id }, { content: req.body.content });
    res.redirect('/profile');


});



app.post('/post', isLoggedIn, async (req, res) => {
    try {
        // Find the user based on the logged-in email
        let user = await userModel.findOne({ email: req.user.email });

        if (!user) {
            return res.status(404).send("User not found");
        }

        // Destructure content from the request body



        // Create a new post (await the promise to get the post with _id)
        let post = await postModel.create({
            user: user._id,  // Associate the post with the logged-in user
            content: req.body.content        // Content of the post
        });

        console.log("Created Post:", post);

        // Push the newly created post's _id into the user's posts array
        user.posts.push(post._id);

        console.log("User Posts Array before save:", user.posts);

        // Save the user document with the new post reference
        await user.save();

        console.log("User after save:", user);

        // Redirect to the profile page
        res.redirect('/profile');
    } catch (error) {
        console.error("Error creating post:", error);
        res.status(500).send("An error occurred while creating the post.");
    }
});


app.get('/logout', (req, res) => {
    res.cookie("token", "");
    res.redirect("/login");
})



function isLoggedIn(req, res, next) {
    console.log("Token:", req.cookies.token);
    if (!req.cookies.token) {
        return res.status(401).redirect("/login");
    } else {
        jwt.verify(req.cookies.token, "shhh", (err, decoded) => {
            if (err) {
                return res.redirect("/login");
            }
            req.user = decoded;
            next();
        });
    }
};

// let token = req.cookies.token;
// if(!token){
//     return res.redirect("/login");
// }
// jwt.verify(token, "shhh", (err, decoded)=>{
//     if(err){
//         return res.redirect("/login");
//     }
//     next();
// })


app.listen(port, () => {
    console.log(`Server is running on port ${port}`);
});