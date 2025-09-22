from flask import Flask, render_template, request
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__)

# ✅ boto3 client now uses credentials from AWS CLI configuration
ec2_client = boto3.client("ec2")  

def get_default_vpc():
    try:
        vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        if vpcs["Vpcs"]:
            return vpcs["Vpcs"][0]["VpcId"]
        return None
    except ClientError as e:
        return None

def get_subnet_for_vpc(vpc_id):
    try:
        subnets = ec2_client.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
        if subnets["Subnets"]:
            return subnets["Subnets"][0]["SubnetId"]
        return None
    except ClientError as e:
        return None

@app.route("/", methods=["GET", "POST"])
def index():
    message = None
    instance_info = None

    if request.method == "POST":
        action = request.form["action"]

        try:
            if action == "create":
                instance_type = request.form["instance_type"]
                ami_id = request.form["ami_id"]
                key_name = request.form["key_name"]
                sg_id = request.form["security_group"]
                instance_name = request.form["instance_name"]

                # ✅ Use default VPC & subnet
                vpc_id = get_default_vpc()
                if not vpc_id:
                    return render_template("index.html", message="⚠️ No default VPC found!")

                subnet_id = get_subnet_for_vpc(vpc_id)
                if not subnet_id:
                    return render_template("index.html", message="⚠️ No subnet found!")

                # ✅ Launch instance
                message = "🚀 Launching EC2 instance..."
                instance = ec2_client.run_instances(
                    ImageId=ami_id,
                    InstanceType=instance_type,
                    KeyName=key_name,
                    SecurityGroupIds=[sg_id],
                    SubnetId=subnet_id,
                    MinCount=1,
                    MaxCount=1,
                    TagSpecifications=[{
                        "ResourceType": "instance",
                        "Tags": [{"Key": "Name", "Value": instance_name}]
                    }]
                )

                instance_id = instance["Instances"][0]["InstanceId"]

                waiter = ec2_client.get_waiter("instance_running")
                waiter.wait(InstanceIds=[instance_id])

                details = ec2_client.describe_instances(InstanceIds=[instance_id])
                inst = details["Reservations"][0]["Instances"][0]

                instance_info = {
                    "id": instance_id,
                    "name": instance_name,
                    "state": inst["State"]["Name"],
                    "public_ip": inst.get("PublicIpAddress", "Pending"),
                    "url": f"https://console.aws.amazon.com/ec2/v2/home#Instances:instanceId={instance_id}"
                }
                message = f"✅ Instance {instance_id} launched successfully!"

            elif action == "destroy":
                instance_id = request.form["instance_id"]
                ec2_client.terminate_instances(InstanceIds=[instance_id])
                waiter = ec2_client.get_waiter("instance_terminated")
                waiter.wait(InstanceIds=[instance_id])

                # Get instance details (tags contain Name)
                details = ec2_client.describe_instances(InstanceIds=[instance_id])
                inst = details["Reservations"][0]["Instances"][0]
                instance_name = None
                for tag in inst.get("Tags", []):
                    if tag["Key"] == "Name":
                        instance_name = tag["Value"]

                instance_info = {
                    "id": instance_id,
                    "name": instance_name if instance_name else "N/A",
                    "state": "terminated",
                    "public_ip": "N/A",
                    "url": f"https://console.aws.amazon.com/ec2/v2/home#Instances:instanceId={instance_id}"
                }

                message = f"❌ Instance {instance_id} ({instance_name}) terminated successfully."

        except ClientError as e:
            message = f"❌ AWS Error: {e}"

    return render_template("index.html", message=message, instance_info=instance_info)

if __name__ == "__main__":
    app.run(debug=True)
