FROM --platform=linux/amd64 amazonlinux:2

# Install necessary tools
RUN yum update -y && \
    yum install -y wget tar gzip unzip

# Create layer directory structure
RUN mkdir -p /opt/java /opt/kotlin

# Install Java (Amazon Corretto) - minimal version
RUN cd /tmp && \
    wget https://corretto.aws/downloads/resources/11.0.21.9.1/amazon-corretto-11.0.21.9.1-linux-x64.tar.gz && \
    tar -xzf amazon-corretto-11.0.21.9.1-linux-x64.tar.gz && \
    mv /tmp/amazon-corretto-11*/* /opt/java/ && \
    rm amazon-corretto-11.0.21.9.1-linux-x64.tar.gz

# Install Kotlin with minimal components
RUN cd /tmp && \
    wget https://github.com/JetBrains/kotlin/releases/download/v1.9.0/kotlin-compiler-1.9.0.zip && \
    unzip kotlin-compiler-1.9.0.zip -d /tmp/kotlin && \
    mkdir -p /opt/kotlin/bin && \
    mv /tmp/kotlin/kotlinc/bin/kotlin* /opt/kotlin/bin/ && \
    mv /tmp/kotlin/kotlinc/lib /opt/kotlin/ && \
    rm kotlin-compiler-1.9.0.zip

# Set up environment
ENV JAVA_HOME=/opt/java
ENV PATH="/opt/java/bin:/opt/kotlin/bin:${PATH}"