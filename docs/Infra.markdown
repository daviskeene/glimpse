# Infrastructure

This version of Glimpse was created using:

- FastAPI
- AWS Lambda
- AWS ECR + Docker

## Build & Deploy

The Glimpse service is supposed to be able to run code in many different languages, such as Pyhon, JavaScript, Go, etc. To make this work, we either need to create a new runtime/function for each supported language, or bundle our language support into one custom continaer image and use that instead of the default AWS Lambda runtime. I decided to implement the latter.

## Creating the Docker Image

I have a `Dockerfile-aws` which I used to define our custom image. We can build the image like so:

```
$ docker build --platform linux/amd64 -t glimpse-lambda -f Dockerfiles/Dockerfile-aws .
```

Once the image is built, we can create a new ECR repository to hold the image:

```
$ aws ecr create-repository --repository-name glimpse-lambda
```

and deploy it:

```
$ aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account_id>.dkr.ecr.us-east-1.amazonaws.com

$ docker tag glimpse-lambda:latest <account_id>.dkr.ecr.us-east-1.amazonaws.com/glimpse-lambda:latest

$ docker push <account_id>.dkr.ecr.us-east-1.amazonaws.com/glimpse-lambda:latest
```

Once this image has been deployed, we can create a new lambda function, and select our uploaded container image to use:

<img src="images/Screenshot 2024-10-23 at 12.49.03 PM.png" />

<img src="images/Screenshot 2024-10-23 at 12.49.54 PM.png" />

Once that's complete, we can make calls to the lambda function. Woo!
