# JDK 17 Manual Install / Rollback Steps

## Prerequisites

- JDK tar.gz uploaded to server: `/opt/sso/install/openjdk-17.0.2_linux-x64_bin.tar.gz`
- Current JDK 11 at: `/opt/sso/java/jdk-11.0.12+7`

---

## Upgrade (Install JDK 17)

```bash
# 1. Check if already installed
/opt/sso/java/jdk-17/bin/java -version

# 2. Extract tar.gz
tar -xzf /opt/sso/install/openjdk-17.0.2_linux-x64_bin.tar.gz -C /opt/sso/java/

# 3. Rename to generic path
mv /opt/sso/java/jdk-17.0.2 /opt/sso/java/jdk-17

# 4. Verify
/opt/sso/java/jdk-17/bin/java -version

# 5. Update bash_profile
cat >> ~/.bash_profile << 'EOF'
export JAVA_HOME=/opt/sso/java/jdk-17
export PATH=$JAVA_HOME/bin:$PATH
EOF

# 6. Activate
source ~/.bash_profile
java -version
```

---

## Restore (Rollback to JDK 11)

```bash
# 1. Remove Java 17 references from bash_profile and bashrc
sed -i '/[Jj]dk.17/d' ~/.bash_profile
sed -i '/[Jj]dk.17/d' ~/.bashrc

# 2. Add Java 11 back
cat >> ~/.bash_profile << 'EOF'
export JAVA_HOME=/opt/sso/java/jdk-11.0.12+7
export PATH=$JAVA_HOME/bin:$PATH
EOF

# 3. Activate
source ~/.bash_profile
java -version
```
