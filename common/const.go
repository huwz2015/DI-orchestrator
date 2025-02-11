package util

const (
	GroupNameLabel      = "group-name"
	JobNameLabel        = "dijob-name"
	ControllerNameLabel = "controller-name"
	ReplicaTypeLabel    = "replica-type"
	PodNameLabel        = "pod-name"
	DDPLearnerTypeLabel = "ddp-learner-type"

	ControllerName  = "di-operator"
	CollectorName   = "collector"
	LearnerName     = "learner"
	DDPLearnerName  = "ddp-learner"
	AggregatorName  = "aggregator"
	CoordinatorName = "coordinator"

	DefaultContainerName = "di-container"
	DefaultPortName      = "di-port"

	DefaultCollectorPort   = 22270
	DefaultLearnerPort     = 22271
	DefaultAggregatorPort  = 22272
	DefaultCoordinatorPort = 22273

	DDPLearnerPortPrefix = "gpu-port"
	DDPLearnerTypeMaster = "ddp-learner-master"
	DDPLearnerTypeWorker = "ddp-learner-worker"

	PodNamespaceEnv   = "KUBERNETES_POD_NAMESPACE"
	PodNameEnv        = "KUBERNETES_POD_NAME"
	CoordinatorURLEnv = "KUBERNETES_COORDINATOR_URL"
	AggregatorURLEnv  = "KUBERNETES_AGGREGATOR_URL"
	ServerURLEnv      = "KUBERNETES_SERVER_URL"

	WorldSize         = "WORLD_SIZE"
	LocalWorldSize    = "LOCAL_WORLD_SIZE"
	StartRank         = "START_RANK"
	MasterAddr        = "MASTER_ADDR"
	MasterPort        = "MASTER_PORT"
	DefaultMasterPort = 10314
)

var (
	DefaultServerURL = "di-server.di-system:8080"
)
