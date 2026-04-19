#!/bin/bash
# EC2 배포 준비 스크립트 (로컬 터미널에서 실행)
# 사전 조건: aws configure 완료, 키페어(.pem) 준비
# 리전: ap-northeast-2 (서울)

set -e

REGION="ap-northeast-2"
KEY_NAME="gamefinder-key"          # 기존 키페어 이름으로 교체
INSTANCE_TYPE="t3.medium"
AMI_ID="ami-0c9c942bd7bf113a2"     # Amazon Linux 2023 (서울)
SG_NAME="gamefinder-flask-sg"

echo "=== 1. 보안 그룹 생성 ==="
SG_ID=$(aws ec2 create-security-group \
  --group-name $SG_NAME \
  --description "GameFinder Flask API Security Group" \
  --region $REGION \
  --query 'GroupId' --output text)

echo "Security Group: $SG_ID"

# HTTP(5000), HTTPS(443), SSH(22) 인바운드 허용
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 22   --cidr 0.0.0.0/0 --region $REGION
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 5000 --cidr 0.0.0.0/0 --region $REGION
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 80   --cidr 0.0.0.0/0 --region $REGION

echo "=== 2. EC2 인스턴스 시작 ==="
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type $INSTANCE_TYPE \
  --key-name $KEY_NAME \
  --security-group-ids $SG_ID \
  --region $REGION \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=gamefinder-flask}]" \
  --user-data '#!/bin/bash
    yum update -y
    yum install -y docker
    systemctl start docker
    systemctl enable docker
    usermod -aG docker ec2-user' \
  --query 'Instances[0].InstanceId' --output text)

echo "Instance ID: $INSTANCE_ID"

echo "=== 3. 인스턴스 실행 대기 ==="
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION

PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --region $REGION \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo ""
echo "✅ EC2 생성 완료!"
echo "   Instance ID : $INSTANCE_ID"
echo "   Public IP   : $PUBLIC_IP"
echo "   SSH 접속    : ssh -i ${KEY_NAME}.pem ec2-user@${PUBLIC_IP}"
echo ""
echo "=== 다음 단계 ==="
echo "1. GitHub Secrets에 아래 값 등록:"
echo "   EC2_HOST     = $PUBLIC_IP"
echo "   EC2_SSH_KEY  = (키페어 .pem 파일 내용 붙여넣기)"
echo "   DOCKERHUB_USERNAME / DOCKERHUB_TOKEN"
echo "   STEAM_API_KEY, REDIS_HOST, DB_HOST, DB_PASSWORD ..."
echo ""
echo "2. git push origin main → GitHub Actions 자동 배포"
