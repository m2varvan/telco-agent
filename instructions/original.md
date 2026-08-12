## **Can Open-Source AI Reduce Enterprise Network Operations Costs?**

**Context:**

* <https://blogs.nvidia.com/blog/nvidia-agentic-ai-blueprints-telco-reasoning-models/>
* **Open Nemotron 3 Large Telco Model Brings Reasoning to Telecom**

**The Ask:** Build prototypes using this: <https://docs.nvidia.com/nemo/agent-toolkit/latest/index.html>

## **Why This Project Matters**

This project combines hands-on AI development with strategic technology evaluation. It will provide practical experience with agentic AI frameworks while generating insights into how enterprises can leverage open-source AI to reduce costs, accelerate innovation, and support network operations use cases.

## **Background**

Artificial Intelligence is increasingly being used to automate operational tasks across enterprise environments. At the same time, organizations are evaluating whether open-source AI models can provide similar capabilities to commercial AI solutions while reducing costs and increasing flexibility.

NVIDIA's Open Nemotron Telco Model and NeMo Agent Toolkit provide an opportunity to explore how open-source AI can be applied to telecom and network operations use cases.

## **Project Objective**

Develop and evaluate an AI-powered Network Incident Triage Assistant that uses open-source AI models to help identify potential causes of network incidents.

The project will also assess the economic and operational trade-offs of deploying open-source AI solutions within an enterprise environment.

## **Project Scope**

### **Technical Component**

Build a prototype AI agent using the NVIDIA NeMo Agent Toolkit that can investigate simulated network incidents using synthetic data.

The prototype will focus on a limited set of predefined network incident scenarios. For example:

* KPI degradation associated with a recent configuration change;
* cell/site outage with correlated alarm history;
* performance degradation affecting neighbouring network elements.

The agent should be capable of reviewing multiple data sources, including:

* Historical alarm data
* Network performance KPIs
* Recent configuration changes

Based on the incident presented, the agent should independently determine which diagnostic tools to use and analyse evidence across multiple data sources. The agent should:

* Investigate the network incident
* Select and invoke relevant diagnostic tools
* Correlate evidence across available data sources
* Identify potential root causes
* Generate a Root Cause Analysis recommendation
* Provide an evidence-based explanation supporting the recommendation
* Indicate the confidence of its assessment and whether further investigation is required

### **Research Component (optional)**

Assess the feasibility of using open-source AI models in enterprise network operations by investigating:

* Open-source versus commercial AI approaches
* Infrastructure requirements for model deployment
* Cost implications of self-hosted AI solutions
* Benefits and limitations of open-source AI in enterprise environments
* Potential telecom and network operations use cases

## **Expected Deliverables**

### **1. AI Agent Prototype**

A working proof-of-concept incident triage assistant built using:

* NVIDIA Open Nemotron Telco Model
* NVIDIA NeMo Agent Toolkit
* Synthetic network operations data

### **2. Demonstration**

A short demonstration showing:

* An example incident
* Data analysed by the agent
* Recommended root cause
* Explanation of the agent's reasoning

### **3. Research Report (optional)**

A concise report summarizing:

* Technical architecture
* Key findings
* Infrastructure considerations
* Cost and economic analysis
* Build-versus-buy considerations
* Enterprise opportunities and risks

### **4. Recommendations**

Recommendations on whether open-source AI could be a viable approach for future Rogers network operations use cases.

## **Success Criteria**

The project will be considered successful if the intern can:

* Build a functional AI agent prototype using open-source tools
* Demonstrate automated incident investigation on synthetic data
* Articulate the costs and benefits of open-source AI adoption
* Identify practical opportunities for enterprise deployment