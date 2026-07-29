# NAT operates asynchronously to handle multi-agent calls, network requests, and parallel tool steps efficiently
import asyncio
from dotenv import load_dotenv
from nat.builder.workflow_builder import WorkflowBuilder

load_dotenv()

async def main():

    workflow = WorkflowBuilder.from_config("workflow.yml").build()
    
    result = await workflow.run("List three major achievements of NVIDIA.")

    print(result)

if __name__ == "__main__":
    asyncio.run(main())