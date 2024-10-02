import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as path from "path";

export class CdkLambdaSeleniumStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const dockerImage = new cdk.aws_ecr_assets.DockerImageAsset(
      this,
      "SeleniumDockerImage",
      {
        directory: path.join(__dirname, "../", "app"),
      }
    );
    new cdk.aws_lambda.DockerImageFunction(this, "SeleniumLambda", {
      functionName: "selenium-lambda",
      code: cdk.aws_lambda.DockerImageCode.fromEcr(dockerImage.repository, {
        tagOrDigest: dockerImage.imageTag,
      }),
      memorySize: 2048,
      timeout: cdk.Duration.seconds(90),
    });
  }
}