# Kubernetes Operator Development Guidelines

> 이 문서는 GitHub Copilot이 Kubernetes Operator 프로젝트에서 일관성 있는 Go 코드를 생성하도록 가이드하는 프롬프트입니다.

## Project Overview

이 프로젝트는 **Go 기반 Kubernetes Operator**로서, CRD를 모니터링하고 SRE Agent와 통신하여 자동화된 의사결정을 수행합니다. Controller Runtime과 Kubebuilder를 사용하여 구현됩니다.

### Key Technologies
- **Go 1.21+**: 주 개발 언어
- **Kubebuilder v3**: Operator 스캐폴딩 및 개발 프레임워크
- **Controller Runtime**: Kubernetes 컨트롤러 라이브러리
- **Client-go**: Kubernetes API 클라이언트
- **Logr**: 구조화된 로깅
- **Ginkgo/Gomega**: 테스팅 프레임워크

## Code Style Guidelines

### 1. Go Code Standards

#### Package Organization
```go
// Package comment describing the purpose
package v1alpha1

import (
	// Standard library imports first
	"context"
	"fmt"
	"time"

	// Third-party imports
	"github.com/go-logr/logr"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"

	// Local imports
	sreagentv1alpha1 "github.com/k8s-lovers-korea/ai-sre-agent/operator/api/v1alpha1"
)
```

#### Error Handling
Always use explicit error handling with context:

```go
func (r *SRETaskReconciler) reconcileTask(ctx context.Context, task *sreagentv1alpha1.SRETask) error {
	log := r.Log.WithValues("sretask", task.Name, "namespace", task.Namespace)

	if err := r.validateTask(ctx, task); err != nil {
		log.Error(err, "failed to validate SRE task")
		return fmt.Errorf("task validation failed: %w", err)
	}

	if err := r.processTask(ctx, task); err != nil {
		log.Error(err, "failed to process SRE task")
		return fmt.Errorf("task processing failed: %w", err)
	}

	return nil
}
```

#### Interface Design
Define clear interfaces for testability:

```go
// SREAgentClient defines the interface for communicating with SRE Agent
type SREAgentClient interface {
	RequestDecision(ctx context.Context, req DecisionRequest) (*DecisionResponse, error)
	ExecuteAction(ctx context.Context, req ActionRequest) (*ActionResponse, error)
	HealthCheck(ctx context.Context) error
}

// HTTPSREAgentClient implements SREAgentClient
type HTTPSREAgentClient struct {
	baseURL    string
	httpClient *http.Client
	logger     logr.Logger
}
```

### 2. Kubernetes Custom Resources

#### CRD Structure
Follow Kubernetes API conventions:

```go
// SRETaskSpec defines the desired state of SRETask
type SRETaskSpec struct {
	// Target specifies the Kubernetes resource to monitor
	Target ResourceTarget `json:"target"`

	// Conditions define when to trigger the SRE agent
	Conditions []TriggerCondition `json:"conditions,omitempty"`

	// AgentConfig configures how to interact with SRE agent
	AgentConfig AgentConfiguration `json:"agentConfig,omitempty"`

	// SafetySettings define safety constraints
	SafetySettings SafetyConfiguration `json:"safetySettings,omitempty"`
}

// SRETaskStatus defines the observed state of SRETask
type SRETaskStatus struct {
	// Conditions represent the latest available observations
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// LastTriggered indicates when this task was last triggered
	LastTriggered *metav1.Time `json:"lastTriggered,omitempty"`

	// ActionHistory keeps track of executed actions
	ActionHistory []ActionRecord `json:"actionHistory,omitempty"`

	// Phase represents the current phase of the task
	Phase SRETaskPhase `json:"phase,omitempty"`
}

//+kubebuilder:object:root=true
//+kubebuilder:subresource:status
//+kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
//+kubebuilder:printcolumn:name="Last Triggered",type=date,JSONPath=`.status.lastTriggered`
//+kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// SRETask is the Schema for the sretasks API
type SRETask struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   SRETaskSpec   `json:"spec,omitempty"`
	Status SRETaskStatus `json:"status,omitempty"`
}
```

#### Validation Tags
Use proper validation tags:

```go
type ResourceTarget struct {
	// APIVersion of the target resource
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:Pattern="^[a-zA-Z0-9./]+$"
	APIVersion string `json:"apiVersion"`

	// Kind of the target resource
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	Kind string `json:"kind"`

	// Namespace of the target resource (optional for cluster-scoped resources)
	// +kubebuilder:validation:Optional
	Namespace string `json:"namespace,omitempty"`

	// Name of the target resource (optional for watching all resources of a kind)
	// +kubebuilder:validation:Optional
	Name string `json:"name,omitempty"`
}
```

### 3. Controller Implementation

#### Reconciler Pattern
```go
// SRETaskReconciler reconciles a SRETask object
type SRETaskReconciler struct {
	client.Client
	Log          logr.Logger
	Scheme       *runtime.Scheme
	AgentClient  SREAgentClient
	EventManager EventManager
}

//+kubebuilder:rbac:groups=sreagent.k8s-lovers-korea.io,resources=sretasks,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=sreagent.k8s-lovers-korea.io,resources=sretasks/status,verbs=get;update;patch
//+kubebuilder:rbac:groups=sreagent.k8s-lovers-korea.io,resources=sretasks/finalizers,verbs=update

func (r *SRETaskReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := r.Log.WithValues("sretask", req.NamespacedName)

	// Fetch the SRETask instance
	var task sreagentv1alpha1.SRETask
	if err := r.Get(ctx, req.NamespacedName, &task); err != nil {
		if client.IgnoreNotFound(err) == nil {
			log.Info("SRETask resource not found, ignoring since object must be deleted")
			return ctrl.Result{}, nil
		}
		log.Error(err, "failed to get SRETask")
		return ctrl.Result{}, err
	}

	// Handle deletion
	if task.DeletionTimestamp != nil {
		return r.reconcileDelete(ctx, &task)
	}

	// Handle creation/update
	return r.reconcileNormal(ctx, &task)
}

func (r *SRETaskReconciler) reconcileNormal(ctx context.Context, task *sreagentv1alpha1.SRETask) (ctrl.Result, error) {
	log := r.Log.WithValues("sretask", task.Name, "namespace", task.Namespace)

	// Check if conditions are met
	triggered, err := r.evaluateConditions(ctx, task)
	if err != nil {
		return r.updateStatus(ctx, task, sreagentv1alpha1.SRETaskPhaseError, err.Error())
	}

	if !triggered {
		return ctrl.Result{RequeueAfter: time.Minute * 5}, nil
	}

	// Request decision from SRE agent
	decision, err := r.requestAgentDecision(ctx, task)
	if err != nil {
		return r.updateStatus(ctx, task, sreagentv1alpha1.SRETaskPhaseError, err.Error())
	}

	// Execute approved actions
	if decision.Approved {
		if err := r.executeActions(ctx, task, decision.Actions); err != nil {
			return r.updateStatus(ctx, task, sreagentv1alpha1.SRETaskPhaseError, err.Error())
		}
	}

	return r.updateStatus(ctx, task, sreagentv1alpha1.SRETaskPhaseCompleted, "")
}
```

### 4. Configuration Management

#### Environment-based Config
```go
type OperatorConfig struct {
	// SRE Agent API configuration
	AgentBaseURL    string        `env:"SRE_AGENT_BASE_URL" envDefault:"http://sre-agent:8000"`
	AgentTimeout    time.Duration `env:"SRE_AGENT_TIMEOUT" envDefault:"30s"`
	AgentAPIKey     string        `env:"SRE_AGENT_API_KEY"`

	// Kubernetes configuration
	KubeConfig      string        `env:"KUBECONFIG"`
	LeaderElection  bool          `env:"LEADER_ELECTION" envDefault:"true"`
	MetricsAddr     string        `env:"METRICS_ADDR" envDefault:":8080"`
	ProbeAddr       string        `env:"PROBE_ADDR" envDefault:":8081"`

	// Safety configuration
	DryRunMode      bool          `env:"DRY_RUN_MODE" envDefault:"true"`
	MaxConcurrency  int           `env:"MAX_CONCURRENCY" envDefault:"5"`

	// Logging configuration
	LogLevel        string        `env:"LOG_LEVEL" envDefault:"info"`
	LogFormat       string        `env:"LOG_FORMAT" envDefault:"json"`
}

func LoadConfig() (*OperatorConfig, error) {
	config := &OperatorConfig{}
	if err := env.Parse(config); err != nil {
		return nil, fmt.Errorf("failed to parse environment variables: %w", err)
	}
	return config, nil
}
```

### 5. Testing Patterns

#### Controller Testing
```go
var _ = Describe("SRETask Controller", func() {
	Context("When reconciling a resource", func() {
		const resourceName = "test-resource"

		ctx := context.Background()

		typeNamespacedName := types.NamespacedName{
			Name:      resourceName,
			Namespace: "default",
		}

		BeforeEach(func() {
			By("creating the custom resource for the Kind SRETask")
			resource := &sreagentv1alpha1.SRETask{
				ObjectMeta: metav1.ObjectMeta{
					Name:      resourceName,
					Namespace: "default",
				},
				Spec: sreagentv1alpha1.SRETaskSpec{
					Target: sreagentv1alpha1.ResourceTarget{
						APIVersion: "v1",
						Kind:       "Pod",
						Namespace:  "default",
					},
				},
			}
			Expect(k8sClient.Create(ctx, resource)).To(Succeed())
		})

		AfterEach(func() {
			resource := &sreagentv1alpha1.SRETask{}
			err := k8sClient.Get(ctx, typeNamespacedName, resource)
			Expect(err).NotTo(HaveOccurred())

			By("Cleanup the specific resource instance SRETask")
			Expect(k8sClient.Delete(ctx, resource)).To(Succeed())
		})

		It("should successfully reconcile the resource", func() {
			By("Reconciling the created resource")
			controllerReconciler := &SRETaskReconciler{
				Client:      k8sClient,
				Scheme:      k8sClient.Scheme(),
				AgentClient: &mockSREAgentClient{},
			}

			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())
		})
	})
})
```

### 6. Logging Standards

#### Structured Logging with Logr
```go
func (r *SRETaskReconciler) processTask(ctx context.Context, task *sreagentv1alpha1.SRETask) error {
	log := r.Log.WithValues(
		"sretask", task.Name,
		"namespace", task.Namespace,
		"phase", task.Status.Phase,
	)

	log.Info("processing SRE task",
		"target", task.Spec.Target,
		"conditions", len(task.Spec.Conditions),
	)

	// Process task logic...

	log.Info("SRE task processed successfully",
		"duration", time.Since(start),
		"actionsExecuted", len(actions),
	)

	return nil
}

// Error logging with context
func (r *SRETaskReconciler) handleError(ctx context.Context, task *sreagentv1alpha1.SRETask, err error, msg string) {
	log := r.Log.WithValues("sretask", task.Name, "namespace", task.Namespace)

	log.Error(err, msg,
		"phase", task.Status.Phase,
		"lastTriggered", task.Status.LastTriggered,
	)

	// Record event
	r.EventManager.RecordWarning(task, "ProcessingError", fmt.Sprintf("%s: %v", msg, err))
}
```

### 7. Security and Safety

#### RBAC Definitions
```go
// Ensure proper RBAC markers for all resources the operator needs to access
//+kubebuilder:rbac:groups="",resources=pods,verbs=get;list;watch
//+kubebuilder:rbac:groups="",resources=events,verbs=create;patch
//+kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;update;patch
//+kubebuilder:rbac:groups=sreagent.k8s-lovers-korea.io,resources=sretasks,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=sreagent.k8s-lovers-korea.io,resources=sretasks/status,verbs=get;update;patch
```

#### Safety Checks
```go
func (r *SRETaskReconciler) validateAction(ctx context.Context, action ActionRequest) error {
	// Check if action is in allowlist
	if !r.isActionAllowed(action.Type) {
		return fmt.Errorf("action type '%s' is not in allowlist", action.Type)
	}

	// Validate target resource permissions
	if err := r.validateResourceAccess(ctx, action.Target); err != nil {
		return fmt.Errorf("insufficient permissions for target resource: %w", err)
	}

	// Check safety constraints
	if action.Impact == HighImpact && !r.Config.AllowHighImpact {
		return fmt.Errorf("high impact actions are disabled")
	}

	return nil
}
```

## Project Structure

```
operator/
├── api/
│   └── v1alpha1/           # CRD definitions
├── controllers/            # Reconciler implementations
├── internal/
│   ├── agent/             # SRE Agent client
│   ├── config/            # Configuration management
│   └── webhook/           # Admission webhooks (future)
├── pkg/
│   ├── conditions/        # Condition evaluation logic
│   └── safety/           # Safety validation
├── config/
│   ├── crd/              # Generated CRD manifests
│   ├── rbac/             # RBAC manifests
│   └── samples/          # Example resources
└── main.go               # Entry point
```

## Development Workflow

### Before Implementing New Features

1. **Define CRDs first** using proper Kubernetes API conventions
2. **Implement comprehensive validation** using kubebuilder tags
3. **Add proper RBAC markers** for all required permissions
4. **Include safety checks** for all operations
5. **Write controller tests** using Ginkgo/Gomega
6. **Update documentation** and examples

### Code Review Checklist

- [ ] Proper error handling with context
- [ ] Structured logging with relevant fields
- [ ] RBAC markers for all resource access
- [ ] Validation tags on CRD fields
- [ ] Safety checks for destructive operations
- [ ] Comprehensive unit tests
- [ ] Integration tests for controllers
- [ ] Proper resource cleanup in finalizers

## Common Anti-Patterns to Avoid

❌ **Don't**: Use `fmt.Printf` for logging
✅ **Do**: Use structured logging with logr

❌ **Don't**: Ignore errors from Kubernetes API calls
✅ **Do**: Handle all errors with proper context

❌ **Don't**: Hardcode resource names or namespaces
✅ **Do**: Make everything configurable through CRD specs

❌ **Don't**: Perform operations without proper RBAC
✅ **Do**: Define minimal required permissions

❌ **Don't**: Skip validation on user inputs
✅ **Do**: Validate all CRD fields with kubebuilder tags

❌ **Don't**: Block the reconcile loop with long operations
✅ **Do**: Use background goroutines for long-running tasks

---

*이 가이드라인을 따라 안전하고 효율적인 Kubernetes Operator를 개발하세요.*
