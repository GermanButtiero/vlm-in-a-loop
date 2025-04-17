import json
import torch
import numpy as np
from src.dataset import CocoSegmentationDatasetMRCNN
from src.train import train_model, get_model_instance_segmentation
from src.evaluate import calculate_ap
from main import collate_fn
import os

def run_experiment(
    config,
    device,
    train_proportions=[0.2, 0.35, 0.5, 0.65, 0.8],
    output_json="maskrcnn_experiment_results.json"
):
    results = {
        "train_proportion": [],
        "train_size": [],
        "mean_ap": [],
        "ap_per_class": [],
        "train_loss": [],
        "val_loss": []
    }

    # Load full training dataset
    full_train_dataset = CocoSegmentationDatasetMRCNN(
        config["train_image_dir"],
        config["train_annotation_file"]
    )
    dataset_size = len(full_train_dataset)
    indices = np.random.permutation(dataset_size)
    val_size = int(0.1 * dataset_size)
    val_indices = indices[:val_size]
    train_indices_pool = indices[val_size:]

    # Fixed validation set for early stopping/model selection
    val_split = torch.utils.data.Subset(full_train_dataset, val_indices)
    data_loader_val = torch.utils.data.DataLoader(
        val_split, batch_size=config["batch_size"],
        shuffle=False, collate_fn=collate_fn
    )

    # COCO validation set for final evaluation
    coco_val_dataset = CocoSegmentationDatasetMRCNN(
        config["val_image_dir"],
        config["val_annotation_file"]
    )
    coco_val_loader = torch.utils.data.DataLoader(
        coco_val_dataset, batch_size=config["batch_size"],
        shuffle=False, collate_fn=collate_fn
    )

    for proportion in train_proportions:
        print(f"\n=== Running experiment with {proportion*100:.1f}% of training data ===")
        train_size = int(proportion * len(train_indices_pool))
        train_indices = train_indices_pool[:train_size]
        train_subset = torch.utils.data.Subset(full_train_dataset, train_indices)
        train_loader = torch.utils.data.DataLoader(
            train_subset, batch_size=config["batch_size"],
            shuffle=True, collate_fn=collate_fn
        )

        # Train model
        num_classes = config["num_classes"]
        print("Training model...")
        metrics_epoch = train_model(
            train_loader, data_loader_val, num_classes,
            num_epochs=config["num_epochs"], device=device
        )

        # Load trained model
        model = get_model_instance_segmentation(num_classes=num_classes + 1)
        model.load_state_dict(torch.load(config["model_path"]))
        model.to(device)
        model.eval()

        # Evaluate on COCO validation set
        print("Evaluating model...")
        mean_ap, ap_per_class = calculate_ap(model, coco_val_loader, device, iou_threshold=0.5)
        print(f"Mean Average Precision: {mean_ap:.4f}")

        # Log results
        results["train_proportion"].append(proportion)
        results["train_size"].append(train_size)
        results["mean_ap"].append(float(mean_ap))
        results["ap_per_class"].append([float(ap) for ap in ap_per_class])
        results["train_loss"].append(metrics_epoch["train_loss"])
        results["val_loss"].append(metrics_epoch["val_loss"])

        # Save after each run
        with open(output_json, "w") as f:
            json.dump(results, f, indent=4)

    print(f"\nAll experiments complete. Results saved to {output_json}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Mask R-CNN experiments with different train sizes")
    parser.add_argument("--config", type=str, default="config.json", help="Path to config file")
    parser.add_argument("--output", type=str, default="maskrcnn_experiment_results.json", help="Output JSON file")
    parser.add_argument("--proportions", type=float, nargs="+", default=[0.05, 0.1, 0.2, 0.5, 1.0], help="List of train proportions")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    config = json.load(open(args.config))

    run_experiment(
        config,
        device,
        train_proportions=args.proportions,
        output_json=args.output
    )
    
    #python run_maskrcnn_experiment.py --config config.json --output maskrcnn_experiment_results.json --proportions 0.05 0.1 0.2 0.5 1.0